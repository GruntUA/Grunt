"""Row-level security query filters."""

from sqlalchemy import ColumnElement, Table, and_, false, or_, true
from sqlalchemy.sql import Select

from grunt import log
from grunt.permissions.access import RoleAccess
from grunt.permissions.child import child_conditions, is_child
from grunt.permissions.match import PermissionMatch
from grunt.permissions.reference import reference_conditions
from grunt.permissions.shares import shared_names_clause
from grunt.permissions.user_permissions import build_conditions
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.doctype import DocType


async def apply_permission_filter(
    query: Select,
    table: Table,
    user: User,
    doctype: DocType | Meta,
) -> Select:
    """Restrict *query* to the rows *user* may read - every row-level rule in one place.

    Role ``match`` rules, inherited access, child rows and shares (see
    :func:`_role_and_share_filter`), then User Permissions ANDed on top - they
    narrow shared documents too. Callers must not add User Permissions again:
    ones that had to remember it separately (``grunt.get_all``,
    ``grunt.aggregate``) didn't, and showed rows the list hid.
    """
    query = await _role_and_share_filter(query, table, user, doctype)
    user_permissions = await build_conditions(table, user, doctype)
    return query.where(and_(*user_permissions)) if user_permissions else query


async def _role_and_share_filter(
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

    if is_child(doctype):
        return query.where(await child_conditions(table, user, doctype))

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
