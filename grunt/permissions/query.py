"""Row-level security as one query predicate per action - the single source of
truth for "which rows may this user read / write / delete".

* Lists, counts, reports and pickers AND :func:`read_predicate` onto their
  filters (``grunt.query.sql.where``); a raw, unpermissioned read is one that
  never asks for it.
* A single document is decided by :func:`row_allowed`: the *same* predicate,
  evaluated against that row (``grunt.query.evaluate.matches_linked``) - so a
  document opens exactly when a list would hold it. There is no second,
  per-document implementation of any rule to drift from this one.
"""

from collections.abc import Collection, Mapping
from typing import Any

from grunt.log import log
from grunt.permissions.access import RoleAccess
from grunt.permissions.child import child_predicate, is_child
from grunt.permissions.match import PermissionMatch
from grunt.permissions.reference import reference_predicates
from grunt.permissions.roles import role_access
from grunt.permissions.shares import shared_predicate
from grunt.permissions.user_permissions import user_permission_predicate
from grunt.query.evaluate import matches_linked
from grunt.query.nodes import FALSE, TRUE, Cmp, Expr, Linked, and_, or_
lazy import grunt
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.doctype import DocType
lazy from grunt.query.query import Query
lazy from grunt.store import store_for

# Actions whose access can be inherited (child rows, comments, files): seeing
# what a document holds, never changing it through someone else's rights.
READ_ACTIONS = frozenset({"read", "select"})


async def read_predicate(user: str | None, meta: Meta) -> Expr:
    """The rows of *meta*'s DocType that *user* may read."""
    return await action_predicate(user, meta, "read")


async def action_predicate(
    user: str | None, meta: Meta, action: str, *, row: Mapping[str, Any] | None = None
) -> Expr:
    """The rows of *meta*'s DocType on which *user* may perform *action* - every
    row-level rule in one expression, for any store (SQL compiles it, memory
    evaluates it).

    Role ``match`` rules, inherited access, child rows and shares (see
    :func:`_grants_predicate`), then User Permissions ANDed on top - they narrow
    shared documents too.

    *row* is only a hint for deciding that one row: rules that would otherwise
    enumerate every DocType a reference column holds look at the row's own.
    The predicate stays exact for that row.
    """
    columns = meta.columns
    granted = await _grants_predicate(columns, user, meta, action, row)
    return and_(granted, await user_permission_predicate(columns, user, meta))


async def row_allowed(user: str | None, meta: Meta, action: str, row: Mapping[str, Any]) -> bool:
    """Whether *user* may perform *action* on the document *row* - the
    :func:`action_predicate` evaluated against it.

    A ``Linked`` rule (a Link hop, a share, the parent of a child row or a
    comment) is answered by a query against its DocType. Without a database to
    ask, it fails closed.
    """
    predicate = await action_predicate(user, meta, action, row=row)
    return await matches_linked(predicate, dict(row), _linked_exists)


async def _linked_exists(node: Linked, value: Any) -> bool:
    """Whether *node.doctype* has a row with ``node.select == value`` matching
    ``node.where`` - the per-row form of ``field IN (SELECT select ... WHERE where)``."""
    try:
        grunt.get_session()
    except RuntimeError:
        log.warning("permissions.linked_without_session", doctype=node.doctype)
        return False
    target = await grunt.get_meta(node.doctype)
    if target is None:
        return False
    query = Query(doctype=target.name, where=and_(Cmp(node.select, "eq", value), node.where))
    return await store_for(target).count(query) > 0


async def _grants_predicate(
    columns: Collection[str],
    user: str | None,
    doctype: DocType | Meta,
    action: str,
    row: Mapping[str, Any] | None,
) -> Expr:
    """Rows the user's role permissions allow for *action* via ``match``, plus
    documents shared with the user (``SharedWith``) and, for reading, rows that
    follow another document's access (child rows, ``inherit_permission_from``).

    Safe-by-default: a permission rule whose ``match`` expression can't be
    translated contributes *no* rows (fails closed) rather than being treated
    as unrestricted.
    """
    access = await role_access(doctype, user)
    if access.is_unrestricted:
        return TRUE

    if is_child(doctype):
        if action not in READ_ACTIONS:
            return FALSE  # child rows change only by saving their parent
        return await child_predicate(columns, user, doctype, row=row)

    own = await _own_predicates(columns, user, doctype, access, action)
    ref = (
        await reference_predicates(columns, user, doctype, row=row)
        if action in READ_ACTIONS
        else None
    )
    if own is None and ref is None:
        return TRUE  # unrestricted grant, nothing inherited

    conditions: list[Expr] = []
    shared = await shared_predicate(columns, user, doctype, action)
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

    # No rule for this action matched the user's roles (or every matching
    # rule's `match` was unparseable) and nothing is shared: denies all rows.
    return or_(*conditions)


async def _own_predicates(
    columns: Collection[str],
    user: str | None,
    doctype: DocType | Meta,
    access: RoleAccess,
    action: str,
) -> list[Expr] | None:
    """The role rules granting *action*: ``None`` = unrestricted, ``[]`` = no rows."""
    granting = [perm for perm in access.matching_permissions() if perm.grants(action)]
    if any(not getattr(perm, "match", None) for perm in granting):
        return None
    conditions: list[Expr] = []
    for perm in granting:
        condition = await PermissionMatch(perm.match or "").to_expr(columns, user, doctype)
        if condition is not None:
            conditions.append(condition)
        else:
            log.warning("permissions.match_unparseable", doctype=doctype.name, match=perm.match)
    return conditions
