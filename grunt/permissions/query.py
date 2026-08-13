"""Row-level security query filters."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import Table, false, or_

if TYPE_CHECKING:
    from sqlalchemy.sql import Select

    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType

logger = structlog.get_logger()

# "<field> == <value>" / "<field> != <value>", value is either the bare word
# `user` (→ current user's email) or a single/double-quoted string literal.
# Deliberately narrow — a full boolean-expression-to-SQL compiler is a much
# larger, riskier undertaking; this covers the documented use cases
# ("owner == user", "status == 'draft'") for any field, not just those two.
_MATCH_RE = re.compile(
    r"^(?P<field>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?P<op>==|!=)\s*(?P<value>.+)$"
)


def apply_permission_filter(
    query: Select,
    table: Table,
    user: User,
    doctype: DocType,
) -> Select:
    """Restrict *query* to rows the user's role-permissions allow via `match`.

    Safe-by-default: a permission rule whose `match` expression can't be
    translated to SQL contributes *no* rows (fails closed) rather than being
    treated as unrestricted — the opposite default would let a rule nobody
    could actually enforce quietly expose every row instead of none.
    """
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
        else:
            logger.warning(
                "permissions.match_unparseable", doctype=doctype.name, match=match_expr
            )

    if has_unrestricted:
        return query
    if not conditions:
        # Either no read rule matched this user's roles, or every matching
        # rule's `match` was unparseable — deny all rows rather than guess.
        return query.where(false())

    return query.where(or_(*conditions))


def _parse_match_to_sqlalchemy(match_expr: str, table: Table, user: User):
    """Parse a simple ``field == value`` / ``field != value`` match expression.

    Returns ``None`` when the expression isn't in this narrow supported form
    (arbitrary boolean logic, non-string/non-`user` literals, unknown field)
    — the caller treats that as "can't enforce this rule", not "unrestricted".
    """
    m = _MATCH_RE.match(match_expr.strip())
    if not m:
        return None

    field, op, raw_value = m.group("field"), m.group("op"), m.group("value").strip()
    if not hasattr(table.c, field):
        return None

    if raw_value == "user":
        value: str = user.email
    elif len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in "'\"":
        value = raw_value[1:-1]
    else:
        return None  # numbers, bare names, etc. — outside the supported form

    col = table.c[field]
    return col == value if op == "==" else col != value
