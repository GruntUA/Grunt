"""UserGroup - people to notify, assign or share with together.

A group gives no permissions of its own: it only names its members, whom a
notification, an assignment rule or a share may then reach (membership:
:mod:`grunt.permissions.groups`). Everyone may read groups (pickers,
notification rules); user administrators manage them, and a group's
``manager`` may change who is in it.
"""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import _user_ctx
from grunt.permissions.groups import MAX_GROUP_NAME
from grunt.permissions.perms import has_perm


class UserGroup(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    group_name: str  # Name
    manager: str | None  # Manager
    description: str | None  # Description
    users: list[dict]  # Table: UserGroupMember

    # end: auto-generated types

    async def validate(self) -> None:
        name = self.get("group_name") or ""
        if "]" in name:
            # ``@[Group name]`` in a comment ends at the first "]".
            throw(_("A group name can't contain “]”"), "VALIDATION_ERROR")
        if name != name.strip():
            # The name is the group's id: a padded one would never match a mention.
            throw(_("A group name can't start or end with a space"), "VALIDATION_ERROR")
        if len(name) > MAX_GROUP_NAME:
            throw(
                _("A group name is at most %(count)d characters") % {"count": MAX_GROUP_NAME},
                "VALIDATION_ERROR",
            )
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
