"""``auth_providers`` (hooks.py): provider classes declared by path, imported on first access."""

import sys
import types

import pytest

from grunt.apps.consumers import HOOK_CONSUMERS, LoadContext
from grunt.auth.providers import declarations, registry
from grunt.auth.providers.base import AuthProvider


def _provider(name: str, label: str) -> type[AuthProvider]:
    class _Provider(AuthProvider):
        kind = "challenge"

        def is_configured(self) -> bool:
            return True

        async def begin(self, ctx):
            return {}

        async def complete(self, ctx):
            raise NotImplementedError

    _Provider.name = name
    _Provider.label = label
    return _Provider


@pytest.fixture
def fake_app(monkeypatch):
    """A module with two provider classes, an empty registry and no pending declarations."""
    mod = types.ModuleType("fake_auth_app")
    mod.Telegram = _provider("telegram", "Telegram")
    mod.Passkey = _provider("webauthn", "App passkey")
    monkeypatch.setitem(sys.modules, "fake_auth_app", mod)
    monkeypatch.setattr(registry, "_PROVIDERS", {})
    monkeypatch.setattr(registry, "_REGISTERED", set())
    monkeypatch.setattr(declarations, "_DECLARED", [])
    return mod


def test_core_declares_the_builtin_providers():
    from grunt import core_hooks

    assert core_hooks.auth_providers == [
        "grunt.auth.providers.webauthn.WebAuthnProvider",
        "grunt.auth.providers.oauth.GoogleProvider",
        "grunt.auth.providers.oauth.MicrosoftProvider",
        "grunt.auth.providers.email_link.EmailLoginProvider",
    ]


def test_hook_declares_and_registry_imports_on_first_access(fake_app, tmp_path):
    ctx = LoadContext(app_name="fake", app_dir=tmp_path)
    HOOK_CONSUMERS["auth_providers"].apply(["fake_auth_app.Telegram"], ctx)

    assert registry._PROVIDERS == {}  # declared, not imported yet
    assert [p.name for p in registry.all_providers()] == ["telegram"]


def test_a_later_declaration_replaces_a_name(fake_app):
    declarations.declare("grunt.auth.providers.webauthn.WebAuthnProvider")
    declarations.declare("fake_auth_app.Passkey")

    assert registry.get("webauthn").label == "App passkey"


def test_a_registered_instance_wins_over_a_declaration(fake_app):
    declarations.declare("fake_auth_app.Telegram")
    mine = _provider("telegram", "Mine")()
    registry.register(mine)

    assert registry.get("telegram") is mine


def test_a_declaration_in_a_later_batch_replaces_an_earlier_one(fake_app):
    """An app's startup handler may read the registry before the next app's hooks load."""
    declarations.declare("grunt.auth.providers.webauthn.WebAuthnProvider")
    assert registry.get("webauthn").label != "App passkey"

    declarations.declare("fake_auth_app.Passkey")
    assert registry.get("webauthn").label == "App passkey"


def test_a_broken_declaration_does_not_drop_the_rest(fake_app):
    declarations.declare("fake_auth_app.Missing")
    declarations.declare("no_such_module.Provider")
    declarations.declare("fake_auth_app.Telegram")

    assert [p.name for p in registry.all_providers()] == ["telegram"]
