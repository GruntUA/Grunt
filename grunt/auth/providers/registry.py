"""In-process registry of authentication providers.

Built-in providers are wired lazily on first access (``_bootstrap``) to avoid
import cycles between ``grunt.app`` / the ``User`` controller / the providers.
Apps can add their own by calling :func:`register` from their ``hooks.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.i18n import _
from grunt.log import log

if TYPE_CHECKING:
    from grunt.auth.providers.base import AuthProvider


_PROVIDERS: dict[str, AuthProvider] = {}
_BOOTSTRAPPED = False


def register(provider: AuthProvider) -> None:
    """Add (or replace) a provider. Idempotent per ``provider.name``."""
    _PROVIDERS[provider.name] = provider
    log.debug("auth.provider.registered", provider=provider.name)


def _bootstrap() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True  # set first: a failing import must not retry every call
    from grunt.auth.providers import email_link, oauth, webauthn

    webauthn.register_provider()
    oauth.register_providers()
    email_link.register_provider()


def get(name: str) -> AuthProvider:
    """Return the provider or raise a 404 (via ``grunt.throw``)."""
    _bootstrap()
    provider = _PROVIDERS.get(name)
    if provider is None:
        import grunt

        grunt.throw(_("Unknown auth provider: %(name)s") % {"name": name}, "NOT_FOUND")
    return provider


def all_providers() -> list[AuthProvider]:
    _bootstrap()
    return list(_PROVIDERS.values())


def available() -> list[AuthProvider]:
    """Only providers that are actually configured in this deployment."""
    return [p for p in all_providers() if p.is_configured()]


def describe_available() -> list[dict]:
    """Login-screen metadata for every configured provider."""
    return [p.describe() for p in available()]
