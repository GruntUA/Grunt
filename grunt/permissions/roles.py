"""Roles of a user, by email - as ``frappe.get_roles``.

Below the auth layer a user is their email; roles come from here. The user the
context runs as answers from the context (loaded with them on authentication),
the built-in system and guest identities from constants, anyone else from their
``UserRole`` rows.

Distinct from ``permission_checker``/``RoleAccess`` (``rbac.py``/``access.py``),
which are always doctype+action shaped. :func:`has_roles` is the primitive
behind ``@whitelist(roles=[...])`` for RPC-style methods that aren't CRUD
on a single doctype.
"""

from collections.abc import Iterable

from grunt.auth.constants import GUEST_USER_EMAIL, SYSTEM_USER_EMAIL
from grunt.db.api import GruntDB
from grunt.local import _session_ctx, session_roles, session_user
from grunt.permissions.access import RoleAccess, Target

_db = GruntDB()  # stateless: reads through the context's session

_BUILT_IN: dict[str, list[str]] = {
    SYSTEM_USER_EMAIL: ["System Manager"],
    GUEST_USER_EMAIL: ["Guest"],
}


async def get_roles(user: str | None = None) -> list[str]:
    """Role names of *user* (an email); ``None`` - the user the context runs as."""
    if user is None or user == session_user():
        return session_roles()
    if user in _BUILT_IN:
        return list(_BUILT_IN[user])
    if _session_ctx.get() is None:
        return []  # no database in context (a bare unit test): no roles to load
    # UserRole rows hang off the User's name - usually, not always, the email.
    name = await _db.get_value("User", {"email": user}, "name")
    if not name:
        return []
    rows = await _db.get_all(
        "UserRole",
        filters={"parent_name": name, "parent_doctype": "User"},
        fields=["role_name"],
        limit=100,
    )
    return [r["role_name"] for r in rows]


async def has_roles(roles: Iterable[str], *, user: str | None = None) -> bool:
    """True if *user* (an email; ``None`` - the context's) holds any of *roles*."""
    wanted = set(roles)
    return any(r in wanted for r in await get_roles(user))


async def role_access(doctype: Target, user: str | None) -> RoleAccess:
    """:class:`RoleAccess` of *user* (an email; ``None`` - nobody) with their roles."""
    return RoleAccess(doctype, user, await get_roles(user) if user is not None else [])
