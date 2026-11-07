"""Row-level security as a query predicate - ``read_predicate``.

Read paths AND it onto their filters (``grunt.query.sql.where``); a raw,
unpermissioned read is one that never asks for it.
"""

from collections.abc import Collection

from grunt import log
from grunt.permissions.access import RoleAccess
from grunt.permissions.child import child_predicate, is_child
from grunt.permissions.match import PermissionMatch
from grunt.permissions.reference import reference_predicates
from grunt.permissions.shares import shared_predicate
from grunt.permissions.user_permissions import user_permission_predicate
from grunt.query.nodes import TRUE, Expr, and_, or_
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.doctype import DocType


async def read_predicate(user: User, meta: Meta) -> Expr:
    """The rows of *meta*'s DocType that *user* may read - every row-level rule
    in one expression, for any store (SQL compiles it, memory evaluates it).

    Role ``match`` rules, inherited access, child rows and shares (see
    :func:`_role_and_share_predicate`), then User Permissions ANDed on top - they
    narrow shared documents too.
    """
    columns = meta.columns
    roles = await _role_and_share_predicate(columns, user, meta)
    return and_(roles, await user_permission_predicate(columns, user, meta))


async def _role_and_share_predicate(
    columns: Collection[str], user: User, doctype: DocType | Meta
) -> Expr:
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
        return await child_predicate(columns, user, doctype)

    own = await _own_predicates(columns, user, doctype, access)
    ref = await reference_predicates(columns, user, doctype)
    if own is None and ref is None:
        return TRUE  # unrestricted read, nothing inherited

    conditions: list[Expr] = []
    shared = await shared_predicate(columns, user, doctype.name)
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
    columns: Collection[str], user: User, doctype: DocType | Meta, access: RoleAccess
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
        condition = await PermissionMatch(match_expr).to_expr(columns, user, doctype)
        if condition is not None:
            conditions.append(condition)
        else:
            log.warning("permissions.match_unparseable", doctype=doctype.name, match=match_expr)
    return conditions
