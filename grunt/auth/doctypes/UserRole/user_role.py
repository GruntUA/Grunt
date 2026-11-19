"""UserRole DocType controller - child table of ``User.roles``.

A row is a role *assignment*: the role, optionally limited to a scope (documents
linked to ``scope_value`` of ``scope_doctype`` - see
:mod:`grunt.permissions.scopes`) and to a period (``valid_from``..``valid_to``).
"""

from datetime import date
from typing import Any

from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.local import active_role_rows, require_session, system_context
from grunt.permissions.role_props import without_disabled

_db = GruntDB()  # stateless: reads through the context's session

#: What an assignment row carries besides the role.
ROLE_ROW_FIELDS = ["role_name", "scope_doctype", "scope_value", "valid_from", "valid_to"]


class UserRole(Document):
    """DocType controller for UserRole (a child row of ``User.roles``)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    role_name: str  # Role
    scope_doctype: str | None  # Scope
    scope_value: str | None  # Scope value
    valid_from: date | None  # Valid from
    valid_to: date | None  # Valid to

    # end: auto-generated types


def plain_role_row(row: dict[str, Any]) -> dict[str, Any]:
    """*row* with only :data:`ROLE_ROW_FIELDS`, dates as ISO strings - safe to
    cache with the user (``doc_cache`` serialises it)."""
    out: dict[str, Any] = {}
    for field in ROLE_ROW_FIELDS:
        value = row.get(field)
        out[field] = value.isoformat() if isinstance(value, date) else (value or None)
    return out


async def get_user_role_rows(user_id: str) -> list[dict[str, Any]]:
    """Every role assignment of a user, in force or not (see
    :func:`grunt.local.active_role_rows`), but for disabled roles. Caller must
    have an active context."""
    async with system_context(require_session()):
        rows = await _db.get_all(
            "UserRole",
            filters={"parent_name": user_id, "parent_doctype": "User"},
            fields=ROLE_ROW_FIELDS,
            limit=500,
            order_by="idx",
            order="asc",
        )
        rows = await without_disabled(rows)
    return [plain_role_row(r) for r in rows]


async def get_user_roles(user_id: str) -> list[str]:
    """Names of the roles a user holds today. Caller must have an active context."""
    rows = active_role_rows(await get_user_role_rows(user_id))
    return list(dict.fromkeys(r["role_name"] for r in rows))
