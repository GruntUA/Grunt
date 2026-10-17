"""OIDC identity providers (Google, Microsoft) as :class:`AuthProvider`s.

The HTTP surface still lives at ``/api/v1/oauth/{provider}/authorize`` and
``/api/v1/oauth/{provider}/callback`` (the redirect URI registered with the
IdP) - see :mod:`grunt.api.v1.oauth` - but the actual OIDC dance is here so it
goes through the same registry and :func:`grunt.auth.login.issue_login` as
every other method.
"""

import secrets
from typing import Any, ClassVar

import httpx2
from authlib.integrations.httpx_client import AsyncOAuth2Client

from grunt import _
from grunt.api.messages import throw
from grunt.auth.login import find_or_create_external_user
from grunt.auth.providers.base import AuthFlowContext, AuthProvider
from grunt.auth.providers.registry import register
from grunt.config import settings
lazy from grunt.auth.doctypes.User.user import (
    User,
    _apply_signup_approval,
    _guard_registration,
    get_user_by_email,
)

_GOOGLE_CONF_URL = "https://accounts.google.com/.well-known/openid-configuration"
_MICROSOFT_CONF_URL = (
    "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
)
# Multi-tenant endpoints: any Microsoft tenant can sign in through them.
_MICROSOFT_SHARED_TENANTS = frozenset({"common", "organizations", "consumers"})


class OIDCProvider(AuthProvider):
    """Shared Authorization-Code + OIDC-discovery flow."""

    kind: ClassVar = "redirect"
    scope: ClassVar[str] = "openid email profile"

    #: OIDC discovery document URL (may contain ``{tenant}``).
    conf_url: ClassVar[str] = ""

    # deployment config

    def _client_id(self) -> str | None:  # pragma: no cover - trivial
        raise NotImplementedError

    def _client_secret(self) -> str | None:  # pragma: no cover - trivial
        raise NotImplementedError

    def _discovery_url(self) -> str:
        return self.conf_url

    def is_configured(self) -> bool:
        return bool(self._client_id())

    def _callback_url(self) -> str:
        return f"{settings.app_url}/api/v1/oauth/{self.name}/callback"

    # OIDC helpers

    async def _discover(self) -> dict:

        async with httpx2.AsyncClient() as http:
            resp = await http.get(self._discovery_url())
            resp.raise_for_status()
            return resp.json()

    # ceremony

    async def begin(self, ctx: AuthFlowContext) -> dict[str, Any]:
        oidc = await self._discover()
        client = AsyncOAuth2Client(
            client_id=self._client_id(),
            redirect_uri=self._callback_url(),
            scope=self.scope,
        )
        # ``state`` is returned to the caller, which binds it to the browser
        # (an HttpOnly cookie, see grunt.api.v1.oauth) and checks it on the
        # callback - a callback whose state the browser never started is refused.
        state = secrets.token_urlsafe(32)
        url, _ = client.create_authorization_url(oidc["authorization_endpoint"], state=state)
        await client.aclose()  # pyright: ignore[reportAttributeAccessIssue] - httpx2.AsyncClient method
        return {"redirect_url": url, "state": state}

    def _email_is_verified(self, profile: dict[str, Any]) -> bool:
        """Whether the IdP vouches that the signed-in identity owns ``email``.

        An account is matched by email, so an unverified address must never be
        accepted - it would let one identity sign in as another local user.
        """
        verified = profile.get("email_verified")
        return verified is True or str(verified).lower() == "true"

    async def complete(self, ctx: AuthFlowContext) -> User:
        code = ctx.get("code")
        if not code:
            throw(_("Missing OAuth 'code'"), "VALIDATION_ERROR")

        oidc = await self._discover()
        oa = AsyncOAuth2Client(
            client_id=self._client_id(),
            client_secret=self._client_secret(),
            redirect_uri=self._callback_url(),
            scope=self.scope,
        )
        try:
            await oa.fetch_token(oidc["token_endpoint"], code=code, grant_type="authorization_code")
            resp = await oa.get(oidc["userinfo_endpoint"])  # pyright: ignore[reportAttributeAccessIssue]
            resp.raise_for_status()
            profile = resp.json()
        finally:
            await oa.aclose()  # pyright: ignore[reportAttributeAccessIssue]

        email = (profile.get("email") or "").strip()
        if not email:
            throw(_("OAuth provider did not return an email address"), "VALIDATION_ERROR")
        if not self._email_is_verified(profile):
            throw(_("The provider did not confirm this email address"), "UNAUTHORIZED")
        full_name = profile.get("name") or profile.get("given_name") or email.split("@")[0]

        # Same rules as the other sign-in methods (see email_link._resolve_user):
        # an existing account must be active; a new one is subject to the
        # registration switch and admin approval, not provisioned silently.

        existing = await get_user_by_email(email)
        if existing is not None:
            if not existing.is_active:
                throw(_("The account is deactivated"), "UNAUTHORIZED")
            return existing
        await _guard_registration()
        user = await find_or_create_external_user(email, full_name)
        await _apply_signup_approval(user)
        return user


class GoogleProvider(OIDCProvider):
    name = "google"
    label = "Google"
    icon = "google"
    conf_url = _GOOGLE_CONF_URL

    def _client_id(self) -> str | None:
        return settings.oauth_google_client_id

    def _client_secret(self) -> str | None:
        return settings.oauth_google_client_secret


class MicrosoftProvider(OIDCProvider):
    name = "microsoft"
    label = "Microsoft"
    icon = "microsoft"

    def _discovery_url(self) -> str:
        return _MICROSOFT_CONF_URL.format(tenant=settings.oauth_microsoft_tenant_id)

    def _email_is_verified(self, profile: dict[str, Any]) -> bool:
        # Microsoft's userinfo carries no ``email_verified``. An address is
        # trusted only from one configured organisation tenant, whose directory
        # its admins control - never from the multi-tenant endpoints, where the
        # email claim is not verified by Microsoft.
        if super()._email_is_verified(profile):
            return True
        tenant = (settings.oauth_microsoft_tenant_id or "").strip().lower()
        return bool(tenant) and tenant not in _MICROSOFT_SHARED_TENANTS

    def _client_id(self) -> str | None:
        return settings.oauth_microsoft_client_id

    def _client_secret(self) -> str | None:
        return settings.oauth_microsoft_client_secret


def register_providers() -> None:
    register(GoogleProvider())
    register(MicrosoftProvider())
