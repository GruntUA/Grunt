"""Core auth endpoints — login, logout, register, me."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from grunt.api.v1.auth.schemas import (
    MfaLoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UpdateMeRequest,
    UserResponse,
)
from grunt.api.v1.schemas.response import ok
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.service import (
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    revoke_refresh_tokens_for_user,
    rotate_refresh_token,
    verify_mfa_token,
)
from grunt.core.db.session import get_session
from grunt.core.doctypes.user.user import (
    SYSTEM_USER,
    User,
    authenticate,
    create_user,
    get_user_by_email,
    get_user_by_id,
)
from grunt.core.middleware.rate_limit import limiter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

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
        mfa_enabled=bool(user.mfa_enabled),
        avatar=user.avatar,
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
    # If MFA is enabled, issue an MFA token instead of full access/refresh tokens.
    if user.mfa_enabled:
        mfa_token = create_mfa_token(user)
        return TokenResponse(
            mfa_token=mfa_token,
            mfa_required=True,
            user=UserResponse(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                roles=user.roles,
                is_superadmin=user.is_superadmin,
                theme=user.theme,
                avatar=user.avatar,
                mfa_enabled=bool(user.mfa_enabled),
            ),
        )

    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(user.id, session)

    # Track login session
    await _track_session(request, user.id, session)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_superadmin=user.is_superadmin,
            theme=user.theme,
            avatar=user.avatar,
        ),
    )


@router.post("/mfa-login", response_model=TokenResponse)
async def mfa_login_verify(
    request: Request,
    body: MfaLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Verify MFA code using a temporary MFA token and complete login."""
    payload = verify_mfa_token(body.mfa_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Невалідний або прострочений MFA токен")

    user = await get_user_by_id(payload["uid"], session)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Користувача не знайдено")

    from grunt.core.auth.mfa import check_mfa_code  # noqa: PLC0415

    try:
        await check_mfa_code(user, body.code, session)
    except HTTPException as error:
        raise error
    except Exception as exc:
        logger.error("auth.mfa_verify_error", error=str(exc))
        raise HTTPException(status_code=401, detail=f"Помилка перевірки: {str(exc)}") from exc

    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(user.id, session)

    await _track_session(request, user.id, session)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_superadmin=user.is_superadmin,
            theme=user.theme,
            avatar=user.avatar,
        ),
    )


async def _track_session(request: Request, user_id: str, session: AsyncSession):
    """Best-effort session tracking."""
    try:
        from grunt.core.doctypes.user_session.user_session import create_session  # noqa: PLC0415

        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        await create_session(user_id, ip, ua, session)
    except Exception:  # noqa: BLE001
        pass


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(current_user)) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=user.roles,
        is_superadmin=user.is_superadmin,
        theme=user.theme,
        avatar=user.avatar,
        mfa_enabled=bool(user.mfa_enabled),
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateMeRequest,
    user: User = Depends(current_user),
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
        async with grunt.system_context(session):
            await grunt.db.set_value("User", user.id, values)

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
        avatar=updated.avatar,
        mfa_enabled=bool(updated.mfa_enabled),
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
            avatar=user.avatar,
        ),
    )


@router.post("/logout")
async def logout(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Revoke all refresh tokens and terminate all sessions."""
    await revoke_refresh_tokens_for_user(user.id, session)
    try:
        from grunt.core.doctypes.user_session.user_session import (  # noqa: PLC0415
            terminate_all_user_sessions,
        )

        await terminate_all_user_sessions(user.id, session)
    except Exception:  # noqa: BLE001
        pass
    return ok()


@router.get("/sessions")
async def list_sessions(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return all active sessions for the current user."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.doctypes.user.user import SYSTEM_USER  # noqa: PLC0415

    async with grunt.system_context(session):
        sessions = await grunt.get_list(
            "UserSession",
            filters={"user": user.id, "is_active": True},
            fields=["id", "ip_address", "user_agent", "last_active_at", "creation"],
            order_by="last_active_at desc",
        )

    return ok(sessions)


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Terminate a specific session. Only the owner can revoke their own sessions."""
    from grunt.core.doctypes.user_session.user_session import terminate_session  # noqa: PLC0415

    terminated = await terminate_session(session_id, user.id, session)
    if not terminated:
        raise HTTPException(status_code=404, detail="Session not found")
    return ok()
