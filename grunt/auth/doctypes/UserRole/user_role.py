"""UserRole DocType controller."""

from __future__ import annotations

from grunt.document.base import Document


class UserRole(Document):
    """DocType controller for UserRole."""

    user_id: str
    role_name: str


async def get_user_roles(user_id: str) -> list[str]:
    """Load role names for a user. Caller must already have an active grunt context."""
    from grunt.app import grunt
    from grunt.context import require_session

    async with grunt.system_context(require_session()):
        rows = await grunt.db.get_all(
            "UserRole",
            filters={"user_id": user_id},
            fields=["role_name"],
            limit=100,
        )
        return [r["role_name"] for r in rows]
