"""UserRole DocType controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.core.document.base import Document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class UserRole(Document):
    """DocType controller for UserRole."""

    user_id: str
    role_name: str


async def get_user_roles(user_id: str, session: AsyncSession) -> list[str]:
    """Load role names for a user."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.doctypes.user.user import SYSTEM_USER  # noqa: PLC0415

    async with grunt.system_context(session):
        rows = await grunt.db.get_all(
            "UserRole",
            filters={"user_id": user_id},
            fields=["role_name"],
            limit=100,
        )
        return [r["role_name"] for r in rows]
