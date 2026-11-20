"""Document shares - a ``SharedWith`` row grants access to one document.

Whom: exactly one of ``user`` (an email), ``role`` (everyone holding it
today - without its scope: a scope narrows a role's *rules*, a share is a
deliberate choice of this document), ``user_group`` (the group's members)
or ``everyone`` (every signed-in user; guests only ever see a public link,
``DocumentShare``).

What: ``permission = "Read"`` grants read (and select); ``"Write"`` also
grants write; ``can_reshare`` adds ``share`` - passing the document on, at
no higher a level than the sharer's own (``SharedWith`` controller). Until:
``valid_to`` (a date, inclusive) - past it the row grants nothing.

Shares only *add* access on top of role permissions (see
:meth:`grunt.permissions.rbac.PermissionChecker.check` and
:func:`grunt.permissions.query.read_predicate`); they never grant create or
delete, and never apply to a different document.
"""

from collections.abc import Collection
from datetime import date
from typing import Any

from grunt.auth.constants import GUEST_USER_EMAIL
from grunt.local import _session_ctx
from grunt.metadata.registry import doctype_registry
from grunt.query.nodes import FALSE, Cmp, Empty, Expr, In, Linked, and_, or_
from grunt.query.query import Query
lazy from grunt.permissions.groups import user_groups
lazy from grunt.permissions.roles import get_roles
lazy from grunt.permissions.trees import expand_tree_values
lazy from grunt.store.lookup import store_for

# action -> what a share row must hold to grant it
_GRANTS: dict[str, Expr] = {
    "read": In("permission", ("Read", "Write")),
    "select": In("permission", ("Read", "Write")),
    "write": Cmp("permission", "eq", "Write"),
    "share": Cmp("can_reshare", "eq", True),
}

SHAREABLE_ACTIONS = frozenset(_GRANTS)


async def grants(user: str, doctype: str, action: str, *, on: date | None = None) -> Expr:
    """The ``SharedWith`` rows that grant *user* *action* on *doctype*
    documents, in force *on* a day (today by default) - ``FALSE`` when no
    share grants *action*."""
    return and_(Cmp("reference_doctype", "eq", doctype), await _granting(user, action, on))


async def _granting(user: str, action: str, on: date | None = None) -> Expr:
    """The ``SharedWith`` rows of any DocType that grant *user* *action*, in force *on* a day."""
    level = _GRANTS.get(action)
    if level is None:
        return FALSE
    held = await get_roles(user)
    if user == GUEST_USER_EMAIL or "Guest" in held:
        return FALSE  # a guest sees a document only through a public link
    groups = await user_groups(user)
    whom = or_(
        Cmp("user", "eq", user),
        In("role", tuple(held)) if held else FALSE,
        In("user_group", tuple(groups)) if groups else FALSE,
        Cmp("everyone", "eq", True),
    )
    in_force = or_(Empty("valid_to"), Cmp("valid_to", "gte", on or date.today()))
    return and_(level, whom, in_force)


async def _rows(where: Expr, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    meta = await doctype_registry.get_meta("SharedWith")
    if meta is None:
        return []
    return await store_for(meta).fetch(Query(doctype=meta.name, where=where, fields=fields))


async def has_share(user: str | None, doctype: str, action: str) -> bool:
    """True if *user* holds a share granting *action* on any *doctype* document -
    the DocType-level pre-flight (lists, the ``doc=None`` check). Whether one
    document is shared is part of the row predicate (:func:`shared_predicate`)."""
    # No bound session: a pure in-memory check (unit tests, startup) - there is
    # no DB to hold shares, so roles alone decide.
    if action not in _GRANTS or not user or _session_ctx.get() is None:
        return False
    meta = await doctype_registry.get_meta("SharedWith")
    if meta is None:
        return False
    query = Query(doctype=meta.name, where=await grants(user, doctype, action), limit=1)
    return await store_for(meta).count(query) > 0


async def shared_doctypes(user: str | None, doctypes: Collection[str], action: str) -> set[str]:
    """Those of *doctypes* where *user* holds a share granting *action* on some
    document - :func:`has_share` for many DocTypes in one query."""
    if action not in _GRANTS or not user or not doctypes or _session_ctx.get() is None:
        return set()
    meta = await doctype_registry.get_meta("SharedWith")
    if meta is None:
        return set()
    where = and_(In("reference_doctype", tuple(doctypes)), await _granting(user, action))
    query = Query(doctype=meta.name, where=where, group_by=("reference_doctype",))
    rows = await store_for(meta).aggregate(query)
    return {r["reference_doctype"] for r in rows if r.get("reference_doctype")}


async def _subtree_parent_field(doctype: str) -> str | None:
    meta = await doctype_registry.get_meta(doctype)
    if meta is None or not getattr(meta, "shares_cover_subtree", False):
        return None
    return getattr(meta, "tree_parent_field", None) if getattr(meta, "is_tree", False) else None


async def shared_predicate(
    columns: Collection[str], user: str | None, doctype: Any, action: str = "read"
) -> Expr | None:
    """``name`` among the *doctype* documents shared with *user* in a way that
    grants *action*, for list queries and single-document checks alike;
    ``None`` - nothing can be shared (a singleton, an action no share grants)."""
    if action not in _GRANTS or not user or "name" not in columns:
        return None
    if getattr(doctype, "is_singleton", False):
        return None
    if await doctype_registry.get_meta("SharedWith") is None:
        return None
    mine = await grants(user, doctype.name, action)
    if await _subtree_parent_field(doctype.name) is None:
        return Linked("name", "SharedWith", mine, select="reference_id")
    if _session_ctx.get() is None:
        return None
    roots = {row["reference_id"] for row in await _rows(mine, ("reference_id",))}
    if not roots:
        return None
    return In("name", tuple(sorted(await expand_tree_values(doctype.name, roots))))
