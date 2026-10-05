"""UserRole DocType controller - child table of ``User.roles``."""

from __future__ import annotations

from grunt.document.base import Document


class UserRole(Document):
    """DocType controller for UserRole (a child row of ``User.roles``)."""

    role_name: str


async def get_user_roles(user_id: str) -> list[str]:
    """Load role names for a user. Caller must already have an active grunt context."""
    import grunt

    async with grunt.system_context(grunt.get_session()):
        rows = await grunt.db.get_all(
            "UserRole",
            filters={"parent_name": user_id, "parent_doctype": "User"},
            fields=["role_name"],
            limit=100,
        )
        return [r["role_name"] for r in rows]
