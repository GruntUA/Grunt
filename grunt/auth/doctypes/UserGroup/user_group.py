"""UserGroup - people to notify, assign or share with together.

A group gives no permissions: it only names its members. Everyone may read
groups (pickers, notification rules); user administrators manage them, and a
group's ``manager`` may change who is in it.
"""

from collections.abc import Iterable
from typing import Any

from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import _user_ctx, require_session, system_context
from grunt.permissions.perms import has_perm

_db = GruntDB()  # stateless: reads through the context's session


class UserGroup(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    group_name: str  # Name
    manager: str | None  # Manager
    description: str | None  # Description
    users: list[dict]  # Table: UserGroupMember

    # end: auto-generated types

    async def validate(self) -> None:
        members = [r for r in self.get("users") or [] if isinstance(r, dict) and r.get("user")]
        unique = list({r["user"]: r for r in members}.values())  # the same person once
        self.users = unique
        before = self.doc_before_save or {}
        if (before.get("manager") or None) != (self.get("manager") or None) and not await _admin():
            throw(_("Only user administrators appoint the group's manager"), "FORBIDDEN")


async def _admin() -> bool:
    current = _user_ctx.get()
    if current is None or not getattr(current, "email", None):
        return True  # internal code: fixtures, migrations
    return await has_perm("grunt.manage_users", user=current.email)


async def group_members(groups: Iterable[str]) -> list[dict[str, Any]]:
    """Active members of *groups*: ``[{"user": name, "email"}]``, each once, in
    group then table order."""
    wanted = [g for g in dict.fromkeys(groups) if g]
    if not wanted:
        return []
    async with system_context(require_session()):
        rows = await _db.get_all(
            "UserGroupMember",
            filters={"parent_name__in": wanted, "parent_doctype": "UserGroup"},
            fields=["parent_name", "user"],
            limit=None,
            order_by="idx",
            order="asc",
        )
        names = list(
            dict.fromkeys(r["user"] for g in wanted for r in rows if r["parent_name"] == g)
        )
        if not names:
            return []
        users = await _db.get_all(
            "User",
            filters={"name__in": names, "is_active": True},
            fields=["name", "email"],
            limit=None,
        )
    email = {u["name"]: u.get("email") for u in users}
    return [{"user": n, "email": email[n]} for n in names if email.get(n)]


async def group_emails(groups: Iterable[str]) -> list[str]:
    """Emails of the active members of *groups*."""
    return [m["email"] for m in await group_members(groups)]
