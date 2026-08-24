"""Core auth endpoints — login, logout, register, me."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from grunt.api.router import GruntRouter
from grunt.api.v1.auth.schemas import (
    MfaLoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UpdateMeRequest,
    UserResponse,
)
from grunt.api.v1.schemas.response import ok
from grunt.auth.dependencies import current_user
from grunt.auth.doctypes.User.user import (
    User,
    authenticate,
    create_user,
    get_user_by_email,
    get_user_by_id,
)
from grunt.auth.service import (
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    revoke_refresh_tokens_for_user,
    rotate_refresh_token,
    verify_mfa_token,
)
from grunt.db.session import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

router = GruntRouter(optional_auth=True)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest) -> UserResponse:
    """Register a new user."""
    existing = await get_user_by_email(body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{body.email}' already exists",
        )
    name_parts = body.full_name.split(maxsplit=1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    user = await create_user(body.email, body.password, first_name, last_name, None)
    return UserResponse.from_user(user)


@router.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
) -> TokenResponse:
    """OAuth2 password grant."""
    try:
        user = await authenticate(form_data.username, form_data.password)
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
            user=UserResponse.from_user(user),
        )

    assert user.id is not None
    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(user.id)

    # Track login session
    await _track_session(request, user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.from_user(user),
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

    user = await get_user_by_id(payload["uid"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Користувача не знайдено")

    from grunt.auth.mfa import check_mfa_code

    try:
        await check_mfa_code(user, body.code, session)
    except HTTPException as error:
        raise error
    except Exception as exc:
        logger.error("auth.mfa_verify_error", error=str(exc))
        raise HTTPException(status_code=401, detail=f"Помилка перевірки: {str(exc)}") from exc

    assert user.id is not None
    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(user.id)

    await _track_session(request, user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.from_user(user),
    )


async def _track_session(request: Request, user_id: str):
    """Best-effort session tracking."""
    try:
        from grunt.auth.doctypes.UserSession.user_session import create_session

        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        await create_session(user_id, ip, ua)
    except Exception:
        logger.exception("suppressed_error")


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(current_user)) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse.from_user(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateMeRequest,
    user: User = Depends(current_user),
) -> UserResponse:
    """Update current user preferences."""
    from grunt.app import grunt
    from grunt.context import require_session

    values: dict = {}
    if body.theme is not None:
        if body.theme not in ("light", "dark", "system"):
            raise HTTPException(status_code=422, detail="Invalid theme value")
        values["theme"] = body.theme

    assert user.id is not None
    if values:
        async with grunt.system_context(require_session()):
            await grunt.db.set_value("User", user.id, values)

    updated = await get_user_by_id(user.id)
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.from_user(updated)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    """Exchange a valid refresh token."""
    result = await rotate_refresh_token(body.refresh_token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    new_refresh_token, user = result
    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=new_refresh_token,
        user=UserResponse.from_user(user),
    )


@router.post("/logout")
async def logout(user: User = Depends(current_user)) -> dict:
    """Revoke all refresh tokens and terminate all sessions."""
    assert user.id is not None
    await revoke_refresh_tokens_for_user(user.id)
    try:
        from grunt.auth.doctypes.UserSession.user_session import (
            terminate_all_user_sessions,
        )

        await terminate_all_user_sessions(user.id)
    except Exception:
        logger.exception("suppressed_error")
    return ok()


@router.get("/sessions")
async def list_sessions(user: User = Depends(current_user)) -> dict:
    """Return all active sessions for the current user."""
    from grunt.app import grunt
    from grunt.context import require_session

    async with grunt.system_context(require_session()):
        sessions = await grunt.get_list(
            "UserSession",
            filters={"user": user.id, "is_active": True},
            fields=["name", "ip_address", "user_agent", "last_active_at", "creation"],
            order_by="last_active_at desc",
        )

    return ok(sessions)


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    user: User = Depends(current_user),
) -> dict:
    """Terminate a specific session. Only the owner can revoke their own sessions."""
    from grunt.auth.doctypes.UserSession.user_session import terminate_session

    assert user.id is not None
    terminated = await terminate_session(session_id, user.id)
    if not terminated:
        raise HTTPException(status_code=404, detail="Session not found")
    return ok()
