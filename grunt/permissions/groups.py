"""User groups (``UserGroup``) by membership - who is in a group, which
groups a user is in. Below the permission layer: shares to a group
(:mod:`grunt.permissions.shares`) read it, so it imports nothing from there.
"""

from collections.abc import Iterable
from typing import Any

from grunt.db.api import GruntDB
from grunt.local import _session_ctx

_db = GruntDB()  # stateless: reads through the context's session


# Longest group name - as long as a ``@[Group name]`` comment mention carries
# (UserGroup.validate, grunt.api.v1.document.collaboration).
MAX_GROUP_NAME = 140


async def group_members(groups: Iterable[str]) -> list[dict[str, Any]]:
    """Active members of *groups*: ``[{"user": name, "email"}]``, each once, in
    group then table order."""
    wanted = [g for g in dict.fromkeys(groups) if g]
    if not wanted:
        return []
    rows = await _db.get_all(
        "UserGroupMember",
        filters={"parent_name__in": wanted, "parent_doctype": "UserGroup"},
        fields=["parent_name", "user"],
        limit=None,
        order_by="idx",
        order="asc",
    )
    names = list(dict.fromkeys(r.user for g in wanted for r in rows if r.parent_name == g))
    if not names:
        return []
    users = await _db.get_all(
        "User",
        filters={"name__in": names, "is_active": True},
        fields=["name", "email"],
        limit=None,
    )
    email = {u.name: u.email for u in users}
    return [{"user": n, "email": email[n]} for n in names if email.get(n)]


async def group_emails(groups: Iterable[str]) -> list[str]:
    """Emails of the active members of *groups*."""
    return [m["email"] for m in await group_members(groups)]


async def user_groups(user: str | None) -> list[str]:
    """Names of the groups *user* (an email) is a member of."""
    if not user or _session_ctx.get() is None:
        return []
    # Members are User names - usually, not always, the email.
    name = await _db.get_value("User", {"email": user}, "name")
    if not name:
        return []
    rows = await _db.get_all(
        "UserGroupMember",
        filters={"user": name, "parent_doctype": "UserGroup"},
        pluck="parent_name",
        limit=None,
    )
    return sorted(set(rows))


async def rename_group(**kwargs: Any) -> None:
    """``after_rename`` of ``UserGroup``: the group's name follows its new id
    (Link fields to it are repointed by the rename itself)."""
    new_id = kwargs.get("new_id")
    if new_id:
        await _db.set_value("UserGroup", str(new_id), "group_name", str(new_id))
