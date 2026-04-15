"""FastAPI dependencies for authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from grunt.config import settings
from grunt.core.db.session import get_engine, get_session
from grunt.core.doctypes.user.user import (
    _SESSION_FIELDS,
    GruntUser,
    get_user_by_email,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
_oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def current_user(
    request: Request,
    token: str | None = Depends(_oauth2_scheme_optional),
    session: AsyncSession = Depends(get_session),
) -> GruntUser:
    """Decode JWT or validate an API key and return the authenticated user.

    Auth priority:
    1. ``X-Api-Key: grnt_<key>`` header — static API key (for integrations/CI)
    2. ``Authorization: Bearer <jwt>`` header — standard JWT
    3. ``?token=<jwt>`` query parameter — legacy WebSocket support

    When the JWT contains full identity claims (uid, full_name, etc.) the user
    object is built directly from the payload — zero DB queries.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # ── 1. API Key ────────────────────────────────────────────────────────
    api_key_header = request.headers.get("X-Api-Key")
    if api_key_header:
        from grunt.core.auth.api_key_service import authenticate_api_key  # noqa: PLC0415

        client_ip = request.client.host if request.client else None
        user = await authenticate_api_key(api_key_header, session, client_ip)
        if user is None:
            raise credentials_exception

        from grunt.api.context import set_user  # noqa: PLC0415

        set_user(user)
        return user

    # ── 2. JWT Bearer / query param ───────────────────────────────────────
    if not token:
        token = request.query_params.get("token")
    if not token:
        # print("DEBUG: No token found in headers or query params")
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception from None

    # Fast path: all identity fields are embedded in the token.
    uid: str | None = payload.get("uid")
    user: GruntUser | None
    if uid:
        user = GruntUser(
            id=uid,
            email=email,
            full_name=payload.get("full_name") or "",
            is_superadmin=bool(payload.get("is_superadmin", False)),
            is_active=bool(payload.get("is_active", True)),
            theme=payload.get("theme") or "system",
            roles=payload.get("roles") or [],
        )
    else:
        # Legacy token — fall back to DB lookup (session fields only, no password/mfa secrets).
        user = await get_user_by_email(email, session, fields=_SESSION_FIELDS)
        if user is None:
            raise credentials_exception

    assert user is not None
    if not user.is_active:
        raise credentials_exception

    from grunt.api.context import set_user  # noqa: PLC0415

    set_user(user)
    return user


async def optional_user(
    token: str | None = Depends(_oauth2_scheme_optional),
    session: AsyncSession = Depends(get_session),
) -> GruntUser | None:
    """Return the authenticated user if a valid token is present, else None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str | None = payload.get("sub")
        if not email:
            return None
    except jwt.PyJWTError:
        return None
    user = await get_user_by_email(email, session)
    if user is None or not user.is_active:
        return None
    return user


async def superadmin_user(
    user: GruntUser = Depends(current_user),
) -> GruntUser:
    """Ensure the current user is a superadmin."""
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required",
        )
    return user


async def grunt_context(
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(current_user),
) -> AsyncGenerator[None, Any]:
    """FastAPI dependency that sets up the grunt SDK context for the duration of a request.

    Automatically calls ``grunt.set_context`` before the endpoint runs and
    ``grunt.reset_context`` when it finishes (even on error).

    Usage::

        @router.get("/")
        async def my_endpoint(_: None = Depends(grunt_context)) -> dict:
            items = await grunt.get_list("MyDocType", filters={"status": "Active"})
            return {"data": items}
    """
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.context import _messages_ctx  # noqa: PLC0415

    tokens = grunt.set_context(session, engine, user)
    _messages_ctx.set([])
    try:
        yield
    finally:
        from grunt.api.context import clear_messages, get_messages  # noqa: PLC0415

        messages = get_messages()
        if messages and user:
            try:
                from grunt.api.v1.ws import manager  # noqa: PLC0415

                for msg in messages:
                    await manager.send_to_user(user.email, {"event": "msgprint", "data": msg})
            except Exception:
                pass
        clear_messages()
        grunt.reset_context(tokens)


async def grunt_context_optional(
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser | None = Depends(optional_user),
) -> AsyncGenerator[None, Any]:
    """FastAPI dependency: sets up grunt SDK context for the request, with an optional user."""
    from grunt.app import grunt

    tokens = grunt.set_context(session, engine, user)
    try:
        yield
    finally:
        grunt.reset_context(tokens)
