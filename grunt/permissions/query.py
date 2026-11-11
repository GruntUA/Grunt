"""Row-level security as one query predicate per action - the single source of
truth for "which rows may this user read / write / delete".

* Lists, counts, reports and pickers AND :func:`read_predicate` onto their
  filters (``grunt.query.sql.where``); a raw, unpermissioned read is one that
  never asks for it.
* A single document is decided by :func:`row_allowed`: the *same* predicate,
  evaluated against that row (``grunt.query.evaluate.matches_linked``) - so a
  document opens exactly when a list would hold it. There is no second,
  per-document implementation of any rule to drift from this one.
* :func:`allowed` answers ``permission_checker.check`` (:mod:`grunt.permissions.rbac`).

Access is recursive - a child row follows its parent, a comment the document it
is about - so the rules that inherit it live here, next to the predicate they
call back into:

**Child rows** have no access rules of their own. A row is readable when its
parent document is readable; without a row to look at, a child DocType is
readable when one of the DocTypes that embed it (via a Table field) is. Rows
are never changed directly - only by saving the parent, where its controller
validates them (e.g. User guards its ``roles``).

**Inherited read access** - rows *about* another document (comments, tags,
attachments, files in a folder) are readable by whoever can read that document.
A DocType opts in with ``inherit_permission_from``: a list of sources, each
either a ``[<doctype field>, <id field>]`` pair (comments, attachments) or the
name of a Link field (a file's ``folder``). A row that points at something via
any source is readable when *one* of the documents it points at is - the role's
``match`` doesn't apply to it, though the role still needs a read rule at all.
Rows that point at nothing keep plain role-based access, and so do rows whose
DocType no longer exists; rows whose document was deleted are hidden (as they
are from lists).
"""

from collections.abc import Collection, Mapping
from typing import Any

from grunt.document.meta import Meta
from grunt.local import _session_ctx, session_user
from grunt.log import log
from grunt.metadata.doctype import DocType
from grunt.metadata.registry import doctype_registry
from grunt.permissions import shares
from grunt.permissions.access import RoleAccess
from grunt.permissions.match import PermissionMatch
from grunt.permissions.roles import role_access
from grunt.permissions.shares import shared_predicate
from grunt.permissions.types import PermissionAction
from grunt.permissions.user_permissions import user_permission_predicate
from grunt.query.evaluate import matches_linked
from grunt.query.nodes import FALSE, TRUE, Cmp, Empty, Expr, Linked, and_, or_
from grunt.query.query import Query
lazy from grunt.store.lookup import store_for

# Actions whose access can be inherited (child rows, comments, files): seeing
# what a document holds, never changing it through someone else's rights.
READ_ACTIONS = frozenset({"read", "select"})

# (doctype field, id field) for a dynamic reference; (None, link field) for a Link.
Source = tuple[str | None, str]


async def allowed(
    doctype: DocType | Meta,
    action: PermissionAction,
    doc: dict | None = None,
    *,
    user: str | None = None,
) -> bool:
    """Whether *user* (an email; ``None`` - the user the context runs as) may
    perform *action* on *doctype* (optionally *doc*).

    With *doc* the answer is the row predicate of *action* evaluated against
    it (:func:`row_allowed`) - the very expression a list query filters by, so
    a document opens exactly when a list would hold it.

    ``doc=None`` is the DocType-level pre-flight: may the user perform
    *action* on *some* row - a role grants it (whatever its ``match``), a
    parent of a child DocType is readable, or a document is shared. Rows are
    then narrowed by the predicate.
    """
    if user is None:
        user = session_user()
    if not user:
        return False  # nobody in context: fail closed, even for an "All" row
    access = await role_access(doctype, user)
    if access.is_unrestricted:
        return True
    if doc is not None:
        meta = doctype if isinstance(doctype, Meta) else Meta(doctype)
        return await row_allowed(user, meta, action, doc)
    if is_child(doctype):
        return await child_allowed(user, doctype, action)
    if any(perm.grants(action) for perm in access.matching_permissions()):
        return True
    if action not in shares.SHAREABLE_ACTIONS or getattr(doctype, "is_singleton", False):
        return False
    return await shares.has_share(user, doctype.name, action)


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
    if _session_ctx.get() is None:
        log.warning("permissions.linked_without_session", doctype=node.doctype)
        return False
    target = await doctype_registry.get_meta(node.doctype)
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


# Child rows


def is_child(doctype: Any) -> bool:
    return getattr(getattr(doctype, "doc", doctype), "is_child", False) is True


async def parent_doctypes(child_name: str) -> list[Any]:
    """Metas of the DocTypes whose Table fields hold *child_name* rows."""

    names = {
        dt.name
        for dt in await doctype_registry.list_all()
        if not dt.is_child
        and any(f.has_trait("table") and f.options == child_name for f in dt.fields)
    }
    metas = [await doctype_registry.get_meta(name) for name in sorted(names)]
    return [m for m in metas if m is not None]


async def child_allowed(user: str | None, doctype: Any, action: PermissionAction) -> bool:
    """DocType-level: a child DocType is readable when one of the DocTypes that
    embed it is. A single row is decided by :func:`child_predicate`."""
    if action not in ("read", "select"):
        return False
    for parent_meta in await parent_doctypes(doctype.name):
        if await allowed(parent_meta, "read", user=user):
            return True
    return False


async def child_predicate(
    columns: Collection[str],
    user: str | None,
    doctype: Any,
    *,
    row: Mapping[str, Any] | None = None,
) -> Expr:
    """Rows whose parent document *user* may read. With *row* only its own
    parent DocType is considered (exact for that row)."""
    if "parent_doctype" not in columns or "parent_name" not in columns:
        return FALSE
    parents = await parent_doctypes(doctype.name)
    if row is not None:
        parents = [p for p in parents if p.name == row.get("parent_doctype")]
    readable: list[Expr] = []
    for parent_meta in parents:
        where = await readable_predicate(user, parent_meta)
        if where is not None:
            readable.append(
                and_(
                    Cmp("parent_doctype", "eq", parent_meta.name),
                    Linked("parent_name", parent_meta.name, where),
                )
            )
    return or_(*readable)


# Inherited read access


def reference_sources(doctype: Any) -> list[Source]:
    raw = getattr(getattr(doctype, "doc", doctype), "inherit_permission_from", None) or []
    sources: list[Source] = []
    for item in raw:
        if isinstance(item, str):
            sources.append((None, item))
        elif len(item) == 2:
            sources.append((item[0], item[1]))
    return sources


def _link_target(doctype: Any, fieldname: str) -> str | None:
    meta = getattr(doctype, "doc", doctype)
    field = next((f for f in meta.fields if f.fieldname == fieldname), None)
    return field.options if field is not None and field.has_trait("link") else None


async def reference_readable(user: str | None, doctype: Any, doc: dict[str, Any]) -> bool | None:
    """Whether *user* can read one of the documents *doc* points at.

    ``None`` when *doc* points at nothing (or only at a removed DocType): the
    role's own rules decide then (see module doc).
    """

    bound = False
    for dt_field, id_field in reference_sources(doctype):
        ref_id = doc.get(id_field)
        ref_doctype = doc.get(dt_field) if dt_field else _link_target(doctype, id_field)
        if not ref_id or not ref_doctype:
            continue
        parent_meta = await doctype_registry.get_meta(ref_doctype)
        if parent_meta is None:
            continue
        bound = True
        lookup = parent_meta.name if parent_meta.is_singleton else ref_id
        parent = await store_for(parent_meta).get(lookup, expand=[])
        if parent is not None and await allowed(parent_meta, "read", parent, user=user):
            return True
    return False if bound else None


async def readable_predicate(user: str | None, parent_meta: Any) -> Expr | None:
    """The rows of *parent_meta* that *user* may read, as a predicate on them -
    ``None`` when *user* can't read that DocType at all."""
    if not await allowed(parent_meta, "read", user=user):
        return None
    return await read_predicate(user, parent_meta)


async def reference_predicates(
    columns: Collection[str],
    user: str | None,
    doctype: Any,
    *,
    row: Mapping[str, Any] | None = None,
) -> tuple[Expr, Expr] | None:
    """``(points at nothing, points at a readable document)``, or ``None`` when
    *doctype* doesn't inherit access.

    For a list every DocType the reference column holds is covered; with *row*
    (deciding that one row) only the row's own - exact for it, without reading
    the distinct values of the whole table."""
    sources = [
        (dt_field, id_field)
        for dt_field, id_field in reference_sources(doctype)
        if id_field in columns and (dt_field is None or dt_field in columns)
    ]
    if not sources:
        return None
    unbound: list[Expr] = []
    readable: list[Expr] = []
    for dt_field, id_field in sources:
        if dt_field is None:
            unbound.append(Empty(id_field))
            target = _link_target(doctype, id_field)
            parent_meta = await doctype_registry.get_meta(target) if target else None
            if parent_meta is not None:
                where = await readable_predicate(user, parent_meta)
                if where is not None:
                    readable.append(Linked(id_field, parent_meta.name, where))
            continue
        empty: list[Expr] = [Empty(dt_field), Empty(id_field)]
        if row is not None:
            referenced = [row.get(dt_field)]
        else:
            meta = await doctype_registry.get_meta(doctype.name)
            referenced = await store_for(meta).distinct(dt_field) if meta is not None else []
        for ref_doctype in referenced:
            if not ref_doctype:
                continue
            parent_meta = await doctype_registry.get_meta(ref_doctype)
            if parent_meta is None:
                empty.append(Cmp(dt_field, "eq", ref_doctype))  # orphans of a removed DocType
                continue
            where = await readable_predicate(user, parent_meta)
            if where is not None:
                readable.append(
                    and_(
                        Cmp(dt_field, "eq", ref_doctype), Linked(id_field, parent_meta.name, where)
                    )
                )
        unbound.append(or_(*empty))
    return and_(*unbound), or_(*readable)
