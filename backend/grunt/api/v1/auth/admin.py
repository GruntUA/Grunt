"""User and role management endpoints (superadmin only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from grunt.core.auth.dependencies import superadmin_user
from grunt.core.auth.models import SYSTEM_USER, GruntUser
from grunt.core.db.session import get_engine, get_session
from grunt.core.doctypes.user.user import (
    get_user_by_email,
    get_user_by_id,
    hash_password,
    list_users as service_list_users,
)
from grunt.api.v1.auth.schemas import (
    AddRoleRequest,
    SetPasswordRequest,
    UserResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

router = APIRouter()


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
    from grunt.app import grunt  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        roles = await grunt.db.get_all("Role", fields=["role_name", "description"], limit=1000)
    finally:
        grunt.reset_context(_tokens)
    return {
        "success": True,
        "data": [{"name": r["role_name"], "description": r.get("description")} for r in roles],
    }


@router.post("/roles")
async def create_role(
    body: AddRoleRequest,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Create a new role."""
    from grunt.app import grunt  # noqa: PLC0415

    _tokens = grunt.set_context(session, engine, SYSTEM_USER)
    try:
        existing = await grunt.db.get_all("Role", filters={"role_name": body.role_name}, limit=1)
        if existing:
            raise HTTPException(status_code=409, detail=f"Роль '{body.role_name}' вже існує")
        doc = await grunt.new_doc("Role", {"role_name": body.role_name})
        await session.flush()
    finally:
        grunt.reset_context(_tokens)
    return {"success": True, "data": {"name": doc["role_name"]}}


@router.post("/users/{user_id}/roles")
async def add_user_role(
    user_id: str,
    body: AddRoleRequest,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Assign a role to a user."""
    from grunt.app import grunt  # noqa: PLC0415

    target_user = await get_user_by_id(user_id, session)
    if not target_user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    _tokens = grunt.set_context(session, engine, SYSTEM_USER)
    try:
        if not await grunt.db.get_all("Role", filters={"role_name": body.role_name}, limit=1):
            await grunt.new_doc("Role", {"role_name": body.role_name})

        existing = await grunt.db.get_all(
            "UserRole",
            filters={"user_id": user_id, "role_name": body.role_name},
            limit=1,
        )
        if existing:
            return {"success": True, "message": "Роль вже призначено"}

        await grunt.new_doc("UserRole", {"user_id": user_id, "role_name": body.role_name})
        await session.flush()
    finally:
        grunt.reset_context(_tokens)
    return {"success": True, "data": {"user_id": user_id, "role": body.role_name}}


@router.post("/users/set-password")
async def set_user_password(
    body: SetPasswordRequest,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Change a user's password (superadmin only)."""
    from grunt.app import grunt  # noqa: PLC0415

    user = await get_user_by_email(body.email, session)
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        await grunt.db.set_value("User", user.id, "hashed_password", hash_password(body.password))
    finally:
        grunt.reset_context(_tokens)
    return {"success": True}


@router.delete("/users/{user_id}/roles/{role}")
async def remove_user_role(
    user_id: str,
    role: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Remove a role from a user."""
    from grunt.app import grunt  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        rows = await grunt.db.get_all(
            "UserRole",
            filters={"user_id": user_id, "role_name": role},
            fields=["id"],
            limit=1,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Роль не знайдено у користувача")
        await grunt.db.delete("UserRole", {"id": rows[0]["id"]})
        await session.flush()
    finally:
        grunt.reset_context(_tokens)
    return {"success": True, "message": "Роль знято"}
