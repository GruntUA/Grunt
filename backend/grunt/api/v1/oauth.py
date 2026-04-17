"""OAuth2 / SSO endpoints — Google and Microsoft OIDC.

Requires the ``oauth`` optional extras::

    uv pip install grunt[oauth]

Configuration (in .env or environment variables)::

    OAUTH_GOOGLE_CLIENT_ID=...
    OAUTH_GOOGLE_CLIENT_SECRET=...
    OAUTH_MICROSOFT_CLIENT_ID=...
    OAUTH_MICROSOFT_CLIENT_SECRET=...
    OAUTH_MICROSOFT_TENANT_ID=common   # or specific tenant UUID
    APP_URL=https://app.example.com    # used to build the callback URL

Flow:

1. Frontend redirects user to ``GET /api/v1/oauth/{provider}/authorize``
   which returns the provider's authorization URL.
2. Provider redirects back to ``GET /api/v1/oauth/{provider}/callback?code=...``
3. Backend exchanges code for tokens, fetches the user's profile, finds or
   creates a local User, and returns a Grunt access + refresh token pair.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.config import settings
from grunt.core.auth.dependencies import grunt_context_optional

router = APIRouter(prefix="", tags=["oauth"])

# ── Provider registry ─────────────────────────────────────────────────────────

_GOOGLE_CONF_URL = "https://accounts.google.com/.well-known/openid-configuration"
_MICROSOFT_CONF_URL = (
    "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
)


def _require_authlib():
    try:
        from authlib.integrations.httpx_client import AsyncOAuth2Client

        return AsyncOAuth2Client
    except ImportError as exc:
        raise HTTPException(
            501,
            detail="OAuth requires the 'oauth' extras: uv pip install grunt[oauth]",
        ) from exc


def _callback_url(provider: str) -> str:
    return f"{settings.app_url}/api/v1/oauth/{provider}/callback"


def _get_provider_config(provider: str) -> dict:
    """Return client_id, client_secret, and OIDC discovery URL for the provider."""
    if provider == "google":
        if not settings.oauth_google_client_id:
            raise HTTPException(501, detail="Google OAuth is not configured")
        return {
            "client_id": settings.oauth_google_client_id,
            "client_secret": settings.oauth_google_client_secret,
            "conf_url": _GOOGLE_CONF_URL,
            "scope": "openid email profile",
        }
    if provider == "microsoft":
        if not settings.oauth_microsoft_client_id:
            raise HTTPException(501, detail="Microsoft OAuth is not configured")
        return {
            "client_id": settings.oauth_microsoft_client_id,
            "client_secret": settings.oauth_microsoft_client_secret,
            "conf_url": _MICROSOFT_CONF_URL.format(tenant=settings.oauth_microsoft_tenant_id),
            "scope": "openid email profile",
        }
    raise HTTPException(400, detail=f"Unknown OAuth provider: {provider}")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/{provider}/authorize")
async def oauth_authorize(provider: str) -> dict:
    """Return the authorization URL to redirect the user to.

    The frontend should redirect the browser to ``data.url``.
    """
    oauth_client_cls = _require_authlib()
    cfg = _get_provider_config(provider)

    import httpx

    # Fetch OIDC discovery document to get the authorization_endpoint
    async with httpx.AsyncClient() as http:
        resp = await http.get(cfg["conf_url"])
        resp.raise_for_status()
        oidc = resp.json()

    async with oauth_client_cls(
        client_id=cfg["client_id"],
        redirect_uri=_callback_url(provider),
        scope=cfg["scope"],
    ) as client:
        url, _state = client.create_authorization_url(oidc["authorization_endpoint"])

    return ok({"url": url})


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    _: None = Depends(grunt_context_optional),
) -> dict:
    """Exchange the authorization code for Grunt tokens.

    Returns the same ``TokenResponse`` shape as ``POST /auth/token``.
    """
    oauth_client_cls = _require_authlib()
    cfg = _get_provider_config(provider)

    import httpx

    from grunt.core.auth.service import (
        create_access_token,
        create_refresh_token,
    )
    from grunt.core.doctypes.user.user import (
        create_user,
        get_user_by_email,
    )

    # Fetch OIDC discovery document
    async with httpx.AsyncClient() as http:
        oidc_resp = await http.get(cfg["conf_url"])
        oidc_resp.raise_for_status()
        oidc = oidc_resp.json()

    # Exchange code for tokens and fetch user info
    async with oauth_client_cls(
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        redirect_uri=_callback_url(provider),
        scope=cfg["scope"],
    ) as oa_client:
        await oa_client.fetch_token(
            oidc["token_endpoint"],
            code=code,
            grant_type="authorization_code",
        )
        userinfo = await oa_client.get(oidc["userinfo_endpoint"])
        userinfo.raise_for_status()
        profile = userinfo.json()

    email: str = profile.get("email", "")
    if not email:
        raise HTTPException(422, detail="OAuth provider did not return an email address")

    full_name: str = profile.get("name") or profile.get("given_name") or email.split("@")[0]

    session = grunt._require_session()

    # Find or create the local user
    user = await get_user_by_email(email, session)
    if user is None:
        import secrets

        # Create user with a random unusable password
        user = await create_user(email, secrets.token_hex(32), full_name, session)
        await session.commit()

    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(user.id, session)
    await session.commit()

    return ok(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "mfa_required": user.mfa_enabled,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "roles": user.roles,
                "is_superadmin": user.is_superadmin,
                "theme": user.theme,
            },
        }
    )
