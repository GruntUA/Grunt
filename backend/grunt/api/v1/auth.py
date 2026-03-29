"""Auth API endpoints — register, login, me, user/role management."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntRole, GruntUser, GruntUserRole
from grunt.core.auth.service import (
    authenticate,
    create_access_token,
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
    token_type: str = "bearer"
    user: UserResponse


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


@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """OAuth2 password grant — return access token."""
    user = await authenticate(form_data.username, form_data.password, session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
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
