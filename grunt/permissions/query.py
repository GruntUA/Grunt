"""Row-level security query filters."""

from sqlalchemy import Table
from sqlalchemy.sql import Select

import grunt
from grunt import log
from grunt.permissions.access import RoleAccess
from grunt.permissions.child import child_predicate, is_child
from grunt.permissions.match import PermissionMatch
from grunt.permissions.reference import reference_predicates
from grunt.permissions.shares import shared_predicate
from grunt.permissions.user_permissions import user_permission_predicate
from grunt.query.compile_sql import to_sql
from grunt.query.nodes import TRUE, Expr, and_, linked_doctypes, or_
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.doctype import DocType


async def apply_permission_filter(
    query: Select,
    table: Table,
    user: User,
    doctype: DocType | Meta,
) -> Select:
    """Restrict *query* to the rows *user* may read - :func:`read_predicate` as SQL.

    Callers must not add User Permissions again: they are part of the predicate.
    A wrapper until every read path builds a ``Query`` (DB_LAYERS_PLAN.md, step 3c).
    """
    expr = await read_predicate(table, user, doctype)
    if expr == TRUE:
        return query
    tables: dict[str, Table] = {}
    for name in linked_doctypes(expr):
        meta = await grunt.get_meta(name)
        if meta is None:  # a predicate only names DocTypes it just loaded
            raise LookupError(f"DocType {name!r} disappeared while filtering")
        tables[name] = meta.table
    return query.where(to_sql(expr, table, doctype=doctype.name, tables=tables))


async def read_predicate(table: Table, user: User, doctype: DocType | Meta) -> Expr:
    """The rows of *doctype* (stored in *table*) that *user* may read - every
    row-level rule in one expression.

    Role ``match`` rules, inherited access, child rows and shares (see
    :func:`_role_and_share_predicate`), then User Permissions ANDed on top - they
    narrow shared documents too.
    """
    roles = await _role_and_share_predicate(table, user, doctype)
    return and_(roles, await user_permission_predicate(table, user, doctype))


async def _role_and_share_predicate(table: Table, user: User, doctype: DocType | Meta) -> Expr:
    """Rows the user's role-permissions allow via `match`, plus documents shared
    with the user (``SharedWith``).

    Safe-by-default: a permission rule whose `match` expression can't be
    translated contributes *no* rows (fails closed) rather than being
    treated as unrestricted - the opposite default would let a rule nobody
    could actually enforce quietly expose every row instead of none.
    """
    access = RoleAccess(doctype, user)
    if access.is_unrestricted:
        return TRUE

    if is_child(doctype):
        return await child_predicate(table, user, doctype)

    own = await _own_predicates(table, user, doctype, access)
    ref = await reference_predicates(table, user, doctype)
    if own is None and ref is None:
        return TRUE  # unrestricted read, nothing inherited

    conditions: list[Expr] = []
    shared = await shared_predicate(table, user, doctype.name)
    if shared is not None:
        conditions.append(shared)

    if own is None or own:
        own_cond = TRUE if own is None else or_(*own)
        if ref is None:
            conditions.append(own_cond)
        else:
            # Rows pointing at a document follow its access; the rest, the role's.
            unbound, readable = ref
            conditions.extend([and_(unbound, own_cond), readable])

    # No read rule matched this user's roles (or every matching rule's `match`
    # was unparseable) and nothing is shared: or_() of nothing denies all rows.
    return or_(*conditions)


async def _own_predicates(
    table: Table, user: User, doctype: DocType | Meta, access: RoleAccess
) -> list[Expr] | None:
    """The role read rules: ``None`` = unrestricted, ``[]`` = no rows."""
    if access.has_unrestricted_read:
        return None
    conditions: list[Expr] = []
    for perm in access.matching_permissions():
        if not getattr(perm, "read", False):
            continue
        match_expr = getattr(perm, "match", None)
        if not match_expr:
            return None  # has_unrestricted_read would have said so; defensive only
        condition = await PermissionMatch(match_expr).to_expr(table, user, doctype)
        if condition is not None:
            conditions.append(condition)
        else:
            log.warning("permissions.match_unparseable", doctype=doctype.name, match=match_expr)
    return conditions
