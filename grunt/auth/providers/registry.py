"""In-process registry of authentication providers.

Providers are declared in a hooks module's ``auth_providers`` list - the core's
in :mod:`grunt.core_hooks`, an app's in its ``hooks.py`` - as dotted paths to a
provider class, collected in :mod:`grunt.auth.providers.declarations`. The
registry imports them on first access, not while hooks load: a provider pulls
in the User controller and the login service.

The registry knows no concrete provider, and a provider never imports the
registry. :func:`register` adds a ready instance (tests, ad-hoc code); it wins
over a declared provider of the same name.
"""

import importlib

from grunt.auth.providers.declarations import take
from grunt.errors import throw
from grunt.i18n import _
from grunt.log import log
lazy from grunt.auth.providers.base import AuthProvider

_PROVIDERS: dict[str, AuthProvider] = {}
# Names whose provider came from :func:`register` - a declaration never replaces them.
_REGISTERED: set[str] = set()


def register(provider: AuthProvider) -> None:
    """Add (or replace) a provider instance. Idempotent per ``provider.name``."""
    _PROVIDERS[provider.name] = provider
    _REGISTERED.add(provider.name)
    log.debug("auth.provider.registered", provider=provider.name)


def _load_declared() -> None:
    """Import declared providers. A later declaration of a name wins over an earlier one.

    Each path is imported on its own: a broken one is logged and skipped, the
    rest still load. Taken before importing, so a failure is not retried on
    every call.
    """
    for path in take():
        try:
            module_path, attr = path.rsplit(".", 1)
            provider = getattr(importlib.import_module(module_path), attr)()
        except Exception:
            log.exception("auth.provider.load_failed", path=path)
            continue
        if provider.name not in _REGISTERED:
            _PROVIDERS[provider.name] = provider
            log.debug("auth.provider.declared", provider=provider.name, path=path)


def get(name: str) -> AuthProvider:
    """Return the provider or raise a 404 (via ``grunt.throw``)."""
    _load_declared()
    provider = _PROVIDERS.get(name)
    if provider is None:
        throw(_("Unknown auth provider: %(name)s") % {"name": name}, "NOT_FOUND")
    return provider


def all_providers() -> list[AuthProvider]:
    """Every provider - registered or declared - configured or not."""
    _load_declared()
    return list(_PROVIDERS.values())


def available() -> list[AuthProvider]:
    """Only providers that are actually configured in this deployment."""
    return [p for p in all_providers() if p.is_configured()]


def describe_available() -> list[dict]:
    """Login-screen metadata for every configured provider."""
    return [p.describe() for p in available()]
