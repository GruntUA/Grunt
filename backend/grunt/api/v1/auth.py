"""Auth API endpoints — register, login, me, user/role management."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.middleware.rate_limit import limiter

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntRole, GruntUser, GruntUserRole
from grunt.core.auth.service import (
    consume_password_reset_token,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    revoke_refresh_tokens_for_user,
    rotate_refresh_token,
)
from grunt.core.doctypes.User.User import (
    authenticate,
    create_user,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    list_users as service_list_users,
    _user_table,
)
from grunt.core.db.session import get_session

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    roles: list[str] = []
    is_superadmin: bool = False
    theme: str = "system"
    created_at: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    mfa_required: bool = False  # True when MFA is enabled — client must call POST /mfa/verify


class UpdateMeRequest(BaseModel):
    theme: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Register a new user.  The first user automatically becomes superadmin."""
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


def _rate_limit(limit: str):
    """Decorator that applies slowapi rate limiting when available, no-op otherwise."""
    def decorator(func):  # type: ignore[return]
        if limiter is not None:
            return limiter.limit(limit)(func)
        return func
    return decorator


@router.post("/token", response_model=TokenResponse)
@_rate_limit("20/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """OAuth2 password grant — return access + refresh token pair."""
    try:
        user = await authenticate(form_data.username, form_data.password, session)
    except ValueError as exc:
        if str(exc) == "locked":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked due to too many failed login attempts. Try again later.",
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
    """Update current user preferences (theme, etc.)."""
    from sqlalchemy import update as sa_update  # noqa: PLC0415

    values: dict = {}
    if body.theme is not None:
        if body.theme not in ("light", "dark", "system"):
            raise HTTPException(status_code=422, detail="Invalid theme value")
        values["theme"] = body.theme

    if values:
        table = _user_table()
        await session.execute(sa_update(table).where(table.c.id == user.id).values(**values))
        await session.flush()

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


# ── Refresh token ────────────────────────────────────────────────────────


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
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
    """Revoke all refresh tokens for the current user."""
    await revoke_refresh_tokens_for_user(user.id, session)
    return {"success": True}


# ── Password reset ───────────────────────────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@_rate_limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send a password reset email. Always returns 200 to avoid user enumeration."""
    import structlog  # noqa: PLC0415

    log = structlog.get_logger()
    user = await get_user_by_email(body.email, session)
    if user is None:
        # Don't reveal that the email doesn't exist
        return {"success": True}

    token = await create_password_reset_token(user.id, session)

    from grunt.config import settings  # noqa: PLC0415

    reset_url = f"{settings.app_url}/reset-password?token={token}"

    # Queue email via DocumentService
    try:
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        import uuid as _uuid  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415

        eq_table = compile_doctype_to_table(doctype_registry._doctypes["EmailQueue"])
        now = datetime.now(timezone.utc)
        eq_id = str(_uuid.uuid4())
        await session.execute(
            eq_table.insert().values(
                id=eq_id,
                name=eq_id,
                owner="system",
                created_at=now,
                modified_at=now,
                modified_by="system",
                docstatus=0,
                recipient=user.email,
                subject="Password Reset",
                content=(
                    f"Hello {user.full_name},\n\n"
                    f"Click the link below to reset your password (valid for 1 hour):\n\n"
                    f"{reset_url}\n\n"
                    f"If you did not request a password reset, ignore this email."
                ),
                status="Pending",
            )
        )
        await session.flush()
        log.info("auth.forgot_password", email=user.email)
    except Exception:  # noqa: BLE001
        log.warning("auth.forgot_password_email_queue_failed", email=user.email)

    return {"success": True}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reset password using a valid token."""
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    ok = await consume_password_reset_token(body.token, body.new_password, session)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    return {"success": True}


# ── User & role management (superadmin only) ─────────────────────────────


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> list[UserResponse]:
    """List all users."""
    users = await service_list_users(session)
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            roles=u.roles,
            is_superadmin=u.is_superadmin,
            created_at=u.created_at.isoformat() if u.created_at else None,
        )
        for u in users
    ]


@router.get("/roles")
async def list_roles(
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Return all defined roles."""
    result = await session.execute(select(GruntRole))
    roles = result.scalars().all()
    return {
        "success": True,
        "data": [{"name": r.name, "description": r.description} for r in roles],
    }


class AddRoleRequest(BaseModel):
    role_name: str


@router.post("/roles")
async def create_role(
    body: AddRoleRequest,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Create a new role."""
    existing = await session.execute(
        select(GruntRole).where(GruntRole.name == body.role_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Роль '{body.role_name}' вже існує")
    role = GruntRole(name=body.role_name)
    session.add(role)
    await session.flush()
    return {"success": True, "data": {"name": role.name}}


@router.post("/users/{user_id}/roles")
async def add_user_role(
    user_id: str,
    body: AddRoleRequest,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Assign a role to a user."""
    target_user = await get_user_by_id(user_id, session)
    if not target_user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    # Ensure role exists
    role_result = await session.execute(
        select(GruntRole).where(GruntRole.name == body.role_name)
    )
    if not role_result.scalar_one_or_none():
        role = GruntRole(name=body.role_name)
        session.add(role)
        await session.flush()

    # Check if already assigned
    existing_result = await session.execute(
        select(GruntUserRole).where(
            GruntUserRole.user_id == user_id,
            GruntUserRole.role_name == body.role_name,
        )
    )
    if existing_result.scalar_one_or_none():
        return {"success": True, "message": "Роль вже призначено"}

    user_role = GruntUserRole(user_id=user_id, role_name=body.role_name)
    session.add(user_role)
    await session.flush()
    return {"success": True, "data": {"user_id": user_id, "role": body.role_name}}


class SetPasswordRequest(BaseModel):
    email: str
    password: str


@router.post("/users/set-password")
async def set_user_password(
    body: SetPasswordRequest,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Change a user's password (superadmin only)."""
    from sqlalchemy import update as sa_update  # noqa: PLC0415

    user = await get_user_by_email(body.email, session)
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    table = _user_table()
    await session.execute(
        sa_update(table)
        .where(table.c.id == user.id)
        .values(hashed_password=hash_password(body.password))
    )
    await session.flush()
    return {"success": True}


@router.delete("/users/{user_id}/roles/{role}")
async def remove_user_role(
    user_id: str,
    role: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Remove a role from a user."""
    result = await session.execute(
        select(GruntUserRole).where(
            GruntUserRole.user_id == user_id,
            GruntUserRole.role_name == role,
        )
    )
    user_role = result.scalar_one_or_none()
    if not user_role:
        raise HTTPException(status_code=404, detail="Роль не знайдено у користувача")
    await session.delete(user_role)
    await session.flush()
    return {"success": True, "message": "Роль знято"}


# ── MFA endpoints ─────────────────────────────────────────────────────────


class MfaVerifyRequest(BaseModel):
    code: str


@router.post("/mfa/setup")
async def mfa_setup(
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Start MFA setup — returns a TOTP secret and QR code SVG.

    The secret is saved to the user record but MFA is not yet enabled.
    Call ``POST /mfa/confirm`` with a valid TOTP code to activate.
    """
    from grunt.core.auth.mfa import begin_mfa_setup  # noqa: PLC0415

    info = await begin_mfa_setup(user, session)
    await session.commit()
    return {"success": True, "data": info}


@router.post("/mfa/confirm")
async def mfa_confirm(
    body: MfaVerifyRequest,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Confirm MFA setup by verifying the first TOTP code.

    Returns one-time backup codes that the user must store safely.
    """
    from grunt.core.auth.mfa import confirm_mfa_setup  # noqa: PLC0415

    backup_codes = await confirm_mfa_setup(user, body.code, session)
    await session.commit()
    return {"success": True, "data": {"backup_codes": backup_codes}}


@router.post("/mfa/verify")
async def mfa_verify(
    body: MfaVerifyRequest,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Verify a TOTP or backup code for the authenticated user.

    Used after the primary login when ``requires_mfa: true`` is returned.
    On success, the client can proceed normally — no new token is issued here
    because the user is already authenticated (token was issued at login).
    """
    from grunt.core.auth.mfa import check_mfa_code  # noqa: PLC0415

    await check_mfa_code(user, body.code, session)
    await session.commit()
    return {"success": True}


@router.delete("/mfa/disable")
async def mfa_disable(
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Disable MFA for the current user."""
    from grunt.core.auth.mfa import disable_mfa  # noqa: PLC0415

    await disable_mfa(user, session)
    await session.commit()
    return {"success": True, "message": "MFA вимкнено"}
