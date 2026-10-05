"""OIDC identity providers (Google, Microsoft) as :class:`AuthProvider`s.

The HTTP surface still lives at ``/api/v1/oauth/{provider}/authorize`` and
``/api/v1/oauth/{provider}/callback`` (the redirect URI registered with the
IdP) - see :mod:`grunt.api.v1.oauth` - but the actual OIDC dance is here so it
goes through the same registry and :func:`grunt.auth.login.issue_login` as
every other method.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from authlib.integrations.httpx_client import AsyncOAuth2Client

from grunt import _
from grunt.api.messages import throw
from grunt.auth.login import find_or_create_external_user
from grunt.auth.providers.base import AuthFlowContext, AuthProvider
from grunt.auth.providers.registry import register
from grunt.config import settings

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

_GOOGLE_CONF_URL = "https://accounts.google.com/.well-known/openid-configuration"
_MICROSOFT_CONF_URL = (
    "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
)


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
        import httpx

        async with httpx.AsyncClient() as http:
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
        url, _state = client.create_authorization_url(oidc["authorization_endpoint"])
        await client.aclose()  # pyright: ignore[reportAttributeAccessIssue] - httpx.AsyncClient method
        return {"redirect_url": url}

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

        email = profile.get("email", "")
        if not email:
            throw(_("OAuth provider did not return an email address"), "VALIDATION_ERROR")
        full_name = profile.get("name") or profile.get("given_name") or email.split("@")[0]
        return await find_or_create_external_user(email, full_name)


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

    def _client_id(self) -> str | None:
        return settings.oauth_microsoft_client_id

    def _client_secret(self) -> str | None:
        return settings.oauth_microsoft_client_secret


def register_providers() -> None:
    register(GoogleProvider())
    register(MicrosoftProvider())
