"""FastAPI dependencies for authentication."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.config import settings
from grunt.core.auth.models import GruntUser
from grunt.core.doctypes.User.User import get_user_by_email
from grunt.core.db.session import get_engine, get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
_oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def current_user(
    request: Request,
    token: str | None = Depends(_oauth2_scheme_optional),
    session: AsyncSession = Depends(get_session),
) -> GruntUser:
    """Decode JWT and return the authenticated user, or raise 401."""
    if not token:
        # Fallback to query param 'token' for file downloads (a href)
        token = request.query_params.get("token")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = await get_user_by_email(email, session)
    if user is None or not user.is_active:
        raise credentials_exception
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

    tokens = grunt.set_context(session, engine, user)
    try:
        yield
    finally:
        grunt.reset_context(tokens)

