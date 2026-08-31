"""Generic HTTP surface for pluggable auth providers — mounted at ``/api/v1/auth``.

    GET  /api/v1/auth/methods              → configured providers (login screen)
    POST /api/v1/auth/{name}/begin         → start a sign-in ceremony
    POST /api/v1/auth/{name}/complete      → finish it → standard token payload
    POST /api/v1/auth/{name}/enroll/begin  → add the factor (signed-in user)
    POST /api/v1/auth/{name}/enroll/complete

``complete`` funnels through :func:`grunt.auth.login.issue_login`, so its
response is identical to ``login_api`` (including the ``mfa_required`` gate).
Redirect-style providers (OIDC) also keep their dedicated callback routes in
:mod:`grunt.api.v1.oauth`.
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, Request

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.auth import providers as auth_providers
from grunt.auth.dependencies import current_user, optional_user
from grunt.auth.doctypes.User.user import User
from grunt.auth.login import issue_login
from grunt.auth.providers.base import AuthFlowContext

router = GruntRouter(prefix="", tags=["auth"], optional_auth=True)

_Payload = Body(default=None)


def _ctx(request: Request, data: dict[str, Any] | None, user: User | None) -> AuthFlowContext:
    return AuthFlowContext(
        request=request,
        data=data or {},
        user=user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/methods")
async def list_methods() -> dict:
    """Metadata for every configured provider — drives the login screen."""
    return ok(auth_providers.describe_available())


@router.post("/{name}/begin")
async def begin(
    name: str,
    request: Request,
    payload: dict[str, Any] | None = _Payload,
    user: User | None = Depends(optional_user),
) -> dict:
    provider = auth_providers.get(name)
    return ok(await provider.begin(_ctx(request, payload, user)))


@router.post("/{name}/complete")
async def complete(
    name: str,
    request: Request,
    payload: dict[str, Any] | None = _Payload,
    user: User | None = Depends(optional_user),
) -> dict:
    provider = auth_providers.get(name)
    ctx = _ctx(request, payload, user)
    authed = await provider.complete(ctx)
    return ok(
        await issue_login(authed, ip_address=ctx.ip_address, user_agent=ctx.user_agent)
    )


@router.post("/{name}/enroll/begin")
async def enroll_begin(
    name: str,
    request: Request,
    payload: dict[str, Any] | None = _Payload,
    user: User = Depends(current_user),
) -> dict:
    provider = auth_providers.get(name)
    return ok(await provider.enroll_begin(_ctx(request, payload, user)))


@router.post("/{name}/enroll/complete")
async def enroll_complete(
    name: str,
    request: Request,
    payload: dict[str, Any] | None = _Payload,
    user: User = Depends(current_user),
) -> dict:
    provider = auth_providers.get(name)
    return ok(await provider.enroll_complete(_ctx(request, payload, user)))
