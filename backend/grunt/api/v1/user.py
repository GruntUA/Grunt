"""User management whitelisted methods."""

from __future__ import annotations
from typing import Any
import grunt
from grunt.app import grunt as grunt_app

@grunt.whitelist(allow_guest=True)
async def register(email: str, password: str, full_name: str | None = None) -> dict[str, Any]:
    """Register a new user."""
    from grunt.core.doctypes.user.user import create_user, get_user_by_email
    session = grunt_app._require_session()
    
    existing = await get_user_by_email(email, session)
    if existing is not None:
        grunt_app.throw(f"User with email '{email}' already exists", "CONFLICT")
        
    user = await create_user(email, password, full_name or email, session)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": user.roles,
        "is_superadmin": user.is_superadmin,
    }

@grunt.whitelist()
async def whoami() -> dict[str, Any]:
    """Return the currently authenticated user."""
    user = grunt_app._require_user()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": user.roles,
        "is_superadmin": user.is_superadmin,
    }

@grunt.whitelist()
async def list_users() -> list[dict[str, Any]]:
    """List all users. Superadmin only."""
    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt_app.throw("Unauthorized", "PERMISSION_DENIED")
        
    from grunt.core.doctypes.user.user import list_users as service_list_users
    users = await service_list_users(grunt_app._require_session())
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "roles": u.roles,
            "is_superadmin": u.is_superadmin,
        }
        for u in users
    ]

@grunt.whitelist()
async def add_role(user_id: str, role_name: str) -> dict[str, Any]:
    """Assign a role to a user. Superadmin only."""
    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt_app.throw("Unauthorized", "PERMISSION_DENIED")
        
    from grunt.core.doctypes.user.user import get_user_by_id
    target_user = await get_user_by_id(user_id, grunt_app._require_session())
    if not target_user:
        grunt_app.throw("Користувача не знайдено", "NOT_FOUND")

    # Check if role exists, create if not
    existing_role = await grunt_app.get_list("Role", filters={"role_name": role_name}, limit=1)
    if not existing_role:
        await grunt_app.new_doc("Role", {"role_name": role_name})

    existing_assignment = await grunt_app.get_list(
        "UserRole",
        filters={"user_id": user_id, "role_name": role_name},
        limit=1,
    )
    if existing_assignment:
        return {"user_id": user_id, "role": role_name, "message": "Роль вже призначено"}

    await grunt_app.new_doc("UserRole", {"user_id": user_id, "role_name": role_name})
    return {"user_id": user_id, "role": role_name}

@grunt.whitelist()
async def remove_role(user_id: str, role_name: str) -> bool:
    """Remove a role from a user. Superadmin only."""
    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt_app.throw("Unauthorized", "PERMISSION_DENIED")
        
    rows = await grunt_app.get_list(
        "UserRole",
        filters={"user_id": user_id, "role_name": role_name},
        fields=["id"],
        limit=1,
    )
    if not rows:
        grunt_app.throw("Роль не знайдено у користувача", "NOT_FOUND")
        
    await grunt_app.delete_doc("UserRole", rows[0]["id"])
    return True
