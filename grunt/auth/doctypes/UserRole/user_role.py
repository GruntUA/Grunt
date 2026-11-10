"""UserRole DocType controller - child table of ``User.roles``."""

import grunt
from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.local import require_session

_db = GruntDB()  # stateless: reads through the context's session


class UserRole(Document):
    """DocType controller for UserRole (a child row of ``User.roles``)."""

    role_name: str


async def get_user_roles(user_id: str) -> list[str]:
    """Load role names for a user. Caller must already have an active grunt context."""
    async with grunt.system_context(require_session()):
        rows = await _db.get_all(
            "UserRole",
            filters={"parent_name": user_id, "parent_doctype": "User"},
            fields=["role_name"],
            limit=100,
        )
        return [r["role_name"] for r in rows]
