"""OAuth2 / OIDC redirect endpoints — Google and Microsoft.

The provider logic lives in :mod:`grunt.auth.providers.oauth`; these routes are
just the redirect plumbing the IdP needs (the ``/callback`` path is the
registered redirect URI, so it must keep its shape).

Configuration (``.env`` / environment)::

    OAUTH_GOOGLE_CLIENT_ID=...
    OAUTH_GOOGLE_CLIENT_SECRET=...
    OAUTH_MICROSOFT_CLIENT_ID=...
    OAUTH_MICROSOFT_CLIENT_SECRET=...
    OAUTH_MICROSOFT_TENANT_ID=common
    APP_URL=https://app.example.com

Flow:

1. Frontend fetches ``GET /api/v1/oauth/{provider}/authorize`` and redirects the
   browser to ``data.url``.
2. IdP redirects back to ``GET /api/v1/oauth/{provider}/callback?code=...``.
3. This exchanges the code, finds/creates the local User, then **302-redirects
   the browser back to the SPA** at ``{APP_URL}/login#access_token=...`` (tokens
   in the URL fragment — never sent to a server). ``Login.vue`` consumes the
   fragment, stores the pair and strips it from the URL.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse

from grunt.api.messages import ApplicationError
from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.auth import providers as auth_providers
from grunt.auth.login import issue_login
from grunt.auth.providers.base import AuthFlowContext
from grunt.config import settings

router = GruntRouter(prefix="", tags=["oauth"], optional_auth=True)


def _spa_redirect(fragment: dict[str, str]) -> RedirectResponse:
    base = settings.app_url.rstrip("/")
    return RedirectResponse(f"{base}/login#{urlencode(fragment)}", status_code=302)


@router.get("/{provider}/authorize")
async def oauth_authorize(provider: str, request: Request) -> dict:
    """Return the IdP authorization URL for the frontend to redirect to."""
    prov = auth_providers.get(provider)
    result = await prov.begin(AuthFlowContext(request=request))
    return ok({"url": result["redirect_url"]})


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Exchange the authorization code and bounce back into the SPA."""
    if error or not code:
        return _spa_redirect({"error": error or "missing_code"})

    try:
        prov = auth_providers.get(provider)
        ctx = AuthFlowContext(
            request=request,
            data={"code": code},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        user = await prov.complete(ctx)
        payload = await issue_login(user, ip_address=ctx.ip_address, user_agent=ctx.user_agent)
    except ApplicationError as exc:
        return _spa_redirect({"error": exc.code})

    if payload["mfa_required"]:
        return _spa_redirect({"mfa_token": payload["mfa_token"], "mfa_required": "1"})
    return _spa_redirect(
        {
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
        }
    )
