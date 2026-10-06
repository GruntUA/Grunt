"""Row-level security query filters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Table, and_, false, or_, true

from grunt import log
from grunt.permissions.access import RoleAccess
from grunt.permissions.match import PermissionMatch
from grunt.permissions.reference import reference_conditions
from grunt.permissions.shares import shared_names_clause

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement
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

    own = await _own_conditions(table, user, doctype, access)
    ref = await reference_conditions(table, user, doctype)
    if own is None and ref is None:
        return query  # unrestricted read, nothing inherited

    conditions = []
    shared = await shared_names_clause(table, user, doctype.name)
    if shared is not None:
        conditions.append(shared)

    if own is None or own:
        own_cond = true() if own is None else or_(*own)
        if ref is None:
            conditions.append(own_cond)
        else:
            # Rows pointing at a document follow its access; the rest, the role's.
            unbound, readable = ref
            conditions.extend([and_(unbound, own_cond), readable])

    if not conditions:
        # No read rule matched this user's roles (or every matching rule's
        # `match` was unparseable) and nothing is shared - deny all rows
        # rather than guess.
        return query.where(false())

    return query.where(or_(*conditions))


async def _own_conditions(
    table: Table, user: User, doctype: DocType | Meta, access: RoleAccess
) -> list[ColumnElement[bool]] | None:
    """The role read rules as SQL: ``None`` = unrestricted, ``[]`` = no rows."""
    if access.has_unrestricted_read:
        return None
    conditions: list[ColumnElement[bool]] = []
    for perm in access.matching_permissions():
        if not getattr(perm, "read", False):
            continue
        match_expr = getattr(perm, "match", None)
        if not match_expr:
            return None  # has_unrestricted_read would have said so; defensive only
        condition = await PermissionMatch(match_expr).to_sql(table, user, doctype)
        if condition is not None:
            conditions.append(condition)
        else:
            log.warning("permissions.match_unparseable", doctype=doctype.name, match=match_expr)
    return conditions
