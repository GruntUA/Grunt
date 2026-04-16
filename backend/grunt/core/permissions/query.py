"""Row-level security query filters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Table, or_

if TYPE_CHECKING:
    from sqlalchemy.sql import Select

    from grunt.core.doctypes.user.user import User
    from grunt.core.metadata.doctype import DocType


def apply_permission_filter(
    query: Select,
    table: Table,
    user: User,
    doctype: DocType,
) -> Select:
    if getattr(user, "is_superadmin", False):
        return query

    if not doctype.permissions:
        return query

    user_roles = set(getattr(user, "roles", []) or [])
    conditions = []
    has_unrestricted = False

    for perm in doctype.permissions:
        role = perm.role if hasattr(perm, "role") else ""
        if role not in user_roles and role != "All":
            continue
        read_ok = perm.read if hasattr(perm, "read") else False
        if not read_ok:
            continue

        match_expr = perm.match if hasattr(perm, "match") else None
        if not match_expr:
            has_unrestricted = True
            break

        condition = _parse_match_to_sqlalchemy(match_expr, table, user)
        if condition is not None:
            conditions.append(condition)

    if has_unrestricted or not conditions:
        return query

    return query.where(or_(*conditions))


def _parse_match_to_sqlalchemy(match_expr: str, table: Table, user: User):
    """Parse simple match expressions to SQLAlchemy conditions."""
    expr = match_expr.strip()

    if expr == "owner == user":
        if hasattr(table.c, "owner"):
            return table.c.owner == user.email
    elif expr.startswith("status == "):
        val = expr.split("== ")[1].strip().strip("'\"")
        if hasattr(table.c, "status"):
            return table.c.status == val

    return None  # Can't parse, skip
