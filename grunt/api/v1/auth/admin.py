"""User and role management endpoints (superadmin only)."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from grunt.api.router import GruntRouter
from grunt.api.v1.auth.schemas import (
    AddRoleRequest,
    SetPasswordRequest,
    UserResponse,
)
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.auth.dependencies import superadmin_user
from grunt.auth.doctypes.User.user import (
    get_user_by_email,
    get_user_by_id,
    hash_password,
)
from grunt.auth.doctypes.User.user import (
    list_users as service_list_users,
)

router = GruntRouter(dependencies=[Depends(superadmin_user)])


@router.get("/users", response_model=list[UserResponse])
async def list_users() -> list[UserResponse]:
    """List all users."""
    users = await service_list_users(grunt._require_session())
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
async def list_roles() -> dict:
    """Return all defined roles."""
    roles = await grunt.db.get_all("Role", fields=["role_name", "description"], limit=1000)
    return ok([{"name": r["role_name"], "description": r.get("description")} for r in roles])


@router.post("/roles")
async def create_role(body: AddRoleRequest) -> dict:
    """Create a new role."""
    existing = await grunt.db.get_all("Role", filters={"role_name": body.role_name}, limit=1)
    if existing:
        raise HTTPException(status_code=409, detail=f"Роль '{body.role_name}' вже існує")
    doc = await grunt.new_doc("Role", {"role_name": body.role_name})
    return ok({"name": doc["role_name"]})


@router.post("/users/{user_id}/roles")
async def add_user_role(user_id: str, body: AddRoleRequest) -> dict:
    """Assign a role to a user."""
    target_user = await get_user_by_id(user_id, grunt._require_session())
    if not target_user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    if not await grunt.db.get_all("Role", filters={"role_name": body.role_name}, limit=1):
        await grunt.new_doc("Role", {"role_name": body.role_name})

    existing = await grunt.db.get_all(
        "UserRole",
        filters={"user_id": user_id, "role_name": body.role_name},
        limit=1,
    )
    if existing:
        return ok(message="Роль вже призначено")

    await grunt.new_doc("UserRole", {"user_id": user_id, "role_name": body.role_name})
    return ok({"user_id": user_id, "role": body.role_name})


@router.post("/users/set-password")
async def set_user_password(body: SetPasswordRequest) -> dict:
    """Change a user's password (superadmin only)."""
    user = await get_user_by_email(body.email, grunt._require_session())
    if not user or not user.id:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    await grunt.db.set_value(
        "User", user.id, "hashed_password", await hash_password(body.password)
    )
    return ok()


@router.delete("/users/{user_id}/roles/{role}")
async def remove_user_role(user_id: str, role: str) -> dict:
    """Remove a role from a user."""
    rows = await grunt.db.get_all(
        "UserRole",
        filters={"user_id": user_id, "role_name": role},
        fields=["name"],
        limit=1,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Роль не знайдено у користувача")
    await grunt.db.delete("UserRole", {"name": rows[0]["name"]})
    return ok(message="Роль знято")
