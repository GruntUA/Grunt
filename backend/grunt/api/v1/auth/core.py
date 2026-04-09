"""Core auth endpoints — login, logout, register, me."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from grunt.api.v1.auth.schemas import (
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UpdateMeRequest,
    UserResponse,
)
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import SYSTEM_USER, GruntUser
from grunt.core.auth.service import (
    create_access_token,
    create_refresh_token,
    revoke_refresh_tokens_for_user,
    rotate_refresh_token,
)
from grunt.core.db.session import get_session
from grunt.core.doctypes.user.user import (
    authenticate,
    create_user,
    get_user_by_email,
    get_user_by_id,
)
from grunt.core.middleware.rate_limit import limiter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _rate_limit(limit: str):
    """Decorator that applies slowapi rate limiting when available, no-op otherwise."""

    def decorator(func):
        if limiter is not None:
            return limiter.limit(limit)(func)
        return func

    return decorator


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Register a new user."""
    existing = await get_user_by_email(body.email, session)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{body.email}' already exists",
        )
    user = await create_user(body.email, body.password, body.full_name, session)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=user.roles,
        is_superadmin=user.is_superadmin,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.post("/token", response_model=TokenResponse)
@_rate_limit("20/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """OAuth2 password grant."""
    try:
        user = await authenticate(form_data.username, form_data.password, session)
    except ValueError as exc:
        if str(exc) == "locked":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked. Try again later.",
            ) from exc
        raise
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(user.id, session)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        mfa_required=user.mfa_enabled,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_superadmin=user.is_superadmin,
            theme=user.theme,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def me(user: GruntUser = Depends(current_user)) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=user.roles,
        is_superadmin=user.is_superadmin,
        theme=user.theme,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateMeRequest,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Update current user preferences."""
    from grunt.app import grunt  # noqa: PLC0415

    values: dict = {}
    if body.theme is not None:
        if body.theme not in ("light", "dark", "system"):
            raise HTTPException(status_code=422, detail="Invalid theme value")
        values["theme"] = body.theme

    if values:
        _tokens = grunt.set_context(session, None, SYSTEM_USER)
        try:
            await grunt.db.set_value("User", user.id, values)
        finally:
            grunt.reset_context(_tokens)

    updated = await get_user_by_id(user.id, session)
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=updated.id,
        email=updated.email,
        full_name=updated.full_name,
        roles=updated.roles,
        is_superadmin=updated.is_superadmin,
        theme=updated.theme,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Exchange a valid refresh token."""
    result = await rotate_refresh_token(body.refresh_token, session)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    new_refresh_token, user = result
    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=new_refresh_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_superadmin=user.is_superadmin,
            theme=user.theme,
        ),
    )


@router.post("/logout")
async def logout(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Revoke all refresh tokens."""
    await revoke_refresh_tokens_for_user(user.id, session)
    return {"success": True}
