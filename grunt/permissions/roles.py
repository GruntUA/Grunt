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
from typing import Any

from grunt.auth.constants import GUEST_USER_EMAIL, SYSTEM_USER_EMAIL
from grunt.db.api import GruntDB
from grunt.local import _session_ctx, active_role_rows, session_role_rows, session_user
from grunt.permissions.access import RoleAccess, Scope, Target
from grunt.permissions.role_props import without_disabled

_db = GruntDB()  # stateless: reads through the context's session

#: Principals rules may name besides Role documents: every user, the anonymous one.
#: They ship as standard Role records too, so the role picker offers them.
BUILT_IN_ROLES = frozenset({"All", "Guest"})

_BUILT_IN: dict[str, list[str]] = {
    SYSTEM_USER_EMAIL: ["System Manager"],
    GUEST_USER_EMAIL: ["Guest"],
}

#: What an assignment (a ``UserRole`` row) carries besides the role.
_ROW_FIELDS = ["role_name", "scope_doctype", "scope_value", "valid_from", "valid_to"]


async def get_role_rows(user: str | None = None) -> list[dict[str, Any]]:
    """Role assignments of *user* (an email; ``None`` - the context's) in force
    today, with their scope."""
    if user is None or user == session_user():
        return session_role_rows()
    if user in _BUILT_IN:
        return [{"role_name": r} for r in _BUILT_IN[user]]
    if _session_ctx.get() is None:
        return []  # no database in context (a bare unit test): no roles to load
    # UserRole rows hang off the User's name - usually, not always, the email.
    name = await _db.get_value("User", {"email": user}, "name")
    if not name:
        return []
    rows = await _db.get_all(
        "UserRole",
        filters={"parent_name": name, "parent_doctype": "User"},
        fields=_ROW_FIELDS,
        limit=500,
        order_by="idx",
        order="asc",
    )
    return active_role_rows(await without_disabled(rows))


async def get_roles(user: str | None = None) -> list[str]:
    """Role names of *user* (an email; ``None`` - the user the context runs as)."""
    return list(dict.fromkeys(r["role_name"] for r in await get_role_rows(user)))


def role_scopes(rows: Iterable[dict[str, Any]]) -> dict[str, frozenset[Scope]]:
    """Roles held only within scopes -> their scopes. One assignment without a
    scope makes the role hold everywhere: it isn't in the result then."""
    everywhere: set[str] = set()
    scoped: dict[str, set[Scope]] = {}
    for row in rows:
        role = row["role_name"]
        if row.get("scope_doctype") and row.get("scope_value"):
            scoped.setdefault(role, set()).add((row["scope_doctype"], str(row["scope_value"])))
        else:
            everywhere.add(role)
    return {role: frozenset(found) for role, found in scoped.items() if role not in everywhere}


async def has_roles(roles: Iterable[str], *, user: str | None = None) -> bool:
    """True if *user* (an email; ``None`` - the context's) holds any of *roles*."""
    wanted = set(roles)
    return any(r in wanted for r in await get_roles(user))


async def role_access(doctype: Target, user: str | None) -> RoleAccess:
    """:class:`RoleAccess` of *user* (an email; ``None`` - nobody) with their
    roles and the scopes they hold them in."""
    if user is None:
        return RoleAccess(doctype, user, [])
    rows = await get_role_rows(user)
    roles = list(dict.fromkeys(r["role_name"] for r in rows))
    return RoleAccess(doctype, user, roles, role_scopes(rows))


async def role_holders(roles: Iterable[str], *, active_only: bool = True) -> list[dict[str, Any]]:
    """Who holds any of *roles* today: ``[{"user": id, "email", "roles": {role:
    scopes}}]`` - ``scopes`` empty when the role is held everywhere.

    The one answer to "who has this role" (notifications, assignment, workflow,
    health): an assignment out of its period doesn't count, and *active_only*
    leaves out deactivated users.
    """
    wanted = sorted({r for r in roles if r})
    if not wanted:
        return []
    rows = await _db.get_all(
        "UserRole",
        filters={"role_name__in": wanted, "parent_doctype": "User"},
        fields=["parent_name", *_ROW_FIELDS],
        limit=None,
    )
    by_user: dict[str, list[dict[str, Any]]] = {}
    for row in active_role_rows(await without_disabled(rows)):
        by_user.setdefault(row["parent_name"], []).append(row)
    if not by_user:
        return []
    filters: dict[str, Any] = {"name__in": sorted(by_user)}
    if active_only:
        filters["is_active"] = True
    users = await _db.get_all("User", filters=filters, fields=["name", "email"], limit=None)
    out: list[dict[str, Any]] = []
    for u in sorted(users, key=lambda u: u.name):
        assigned = by_user[u.name]
        scopes = role_scopes(assigned)
        held = {r["role_name"]: scopes.get(r["role_name"], frozenset()) for r in assigned}
        out.append({"user": u.name, "email": u.email, "roles": held})
    return out


async def missing_roles(roles: Iterable[str]) -> list[str]:
    """Those of *roles* that are neither a Role document nor a built-in principal."""
    wanted = sorted({r for r in roles if r and r not in BUILT_IN_ROLES})
    if not wanted:
        return []
    found = set(await _db.get_all("Role", filters={"name__in": wanted}, pluck="name", limit=None))
    return [r for r in wanted if r not in found]
