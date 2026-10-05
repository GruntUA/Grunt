"""Row-level security query filters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Table, false, or_

from grunt import log
from grunt.permissions.access import RoleAccess
from grunt.permissions.match import PermissionMatch

if TYPE_CHECKING:
    from sqlalchemy.sql import Select

    from grunt.auth.doctypes.User.user import User
    from grunt.document.meta import Meta
    from grunt.metadata.doctype import DocType


async def apply_permission_filter(
    query: Select,
    table: Table,
    user: User,
    doctype: DocType | Meta,
) -> Select:
    """Restrict *query* to rows the user's role-permissions allow via `match`,
    plus documents shared with the user (``SharedWith``).

    Safe-by-default: a permission rule whose `match` expression can't be
    translated to SQL contributes *no* rows (fails closed) rather than being
    treated as unrestricted - the opposite default would let a rule nobody
    could actually enforce quietly expose every row instead of none.
    """
    access = RoleAccess(doctype, user)
    if access.is_unrestricted:
        return query

    from grunt.permissions.reference import apply_reference_filter

    query = await apply_reference_filter(query, table, user, doctype)
    if access.has_unrestricted_read:
        return query

    from grunt.permissions.shares import shared_names_clause

    conditions = []
    shared = await shared_names_clause(table, user, doctype.name)
    if shared is not None:
        conditions.append(shared)

    for perm in access.matching_permissions():
        read_ok = perm.read if hasattr(perm, "read") else False
        if not read_ok:
            continue

        match_expr = perm.match if hasattr(perm, "match") else None
        if not match_expr:
            # has_unrestricted_read would have returned above; defensive only.
            return query

        condition = await PermissionMatch(match_expr).to_sql(table, user, doctype)
        if condition is not None:
            conditions.append(condition)
        else:
            log.warning("permissions.match_unparseable", doctype=doctype.name, match=match_expr)

    if not conditions:
        # No read rule matched this user's roles (or every matching rule's
        # `match` was unparseable) and nothing is shared - deny all rows
        # rather than guess.
        return query.where(false())

    return query.where(or_(*conditions))
