"""Document shares - a ``SharedWith`` row grants one user access to one document.

``permission = "Read"`` grants read (and select); ``"Write"`` also grants write.
Shares only *add* access on top of role permissions (see
:meth:`grunt.permissions.rbac.PermissionChecker.check` and
:func:`grunt.permissions.query.read_predicate`); they never grant
create or delete, and never apply to a different document.
"""

from collections.abc import Collection
from typing import Any

from sqlalchemy import select

import grunt
from grunt.local import _session_ctx
from grunt.query.nodes import Cmp, Expr, In, Linked, and_
lazy from grunt.permissions.user_permissions import expand_tree_values

# action -> share levels that grant it
_LEVELS: dict[str, tuple[str, ...]] = {
    "read": ("Read", "Write"),
    "select": ("Read", "Write"),
    "write": ("Write",),
}

SHAREABLE_ACTIONS = frozenset(_LEVELS)


async def has_share(user: str | None, doctype: str, action: str) -> bool:
    """True if *user* holds a share granting *action* on any *doctype* document -
    the DocType-level pre-flight (lists, the ``doc=None`` check). Whether one
    document is shared is part of the row predicate (:func:`shared_predicate`)."""
    levels = _LEVELS.get(action)
    # No bound session: a pure in-memory check (unit tests, startup) - there is
    # no DB to hold shares, so roles alone decide.
    if not levels or not user or _session_ctx.get() is None:
        return False
    filters: dict[str, object] = {
        "reference_doctype": doctype,
        "user": user,
        "permission__in": list(levels),
    }
    return bool(await grunt.db.exists("SharedWith", filters))


async def _subtree_parent_field(doctype: str) -> str | None:
    meta = await grunt.get_meta(doctype)
    if meta is None or not getattr(meta, "shares_cover_subtree", False):
        return None
    return getattr(meta, "tree_parent_field", None) if getattr(meta, "is_tree", False) else None


async def shared_predicate(
    columns: Collection[str], user: str | None, doctype: Any, action: str = "read"
) -> Expr | None:
    """``name`` among the *doctype* documents shared with *user* at a level that
    grants *action*, for list queries and single-document checks alike;
    ``None`` - nothing can be shared (a singleton, an action no share grants)."""
    levels = _LEVELS.get(action)
    if not levels or not user or "name" not in columns:
        return None
    if getattr(doctype, "is_singleton", False):
        return None
    meta = await grunt.get_meta("SharedWith")
    if meta is None:
        return None
    mine = and_(
        Cmp("reference_doctype", "eq", doctype.name),
        Cmp("user", "eq", user),
        In("permission", levels),
    )
    if await _subtree_parent_field(doctype.name) is None:
        return Linked("name", "SharedWith", mine, select="reference_id")
    if _session_ctx.get() is None:
        return None
    share = meta.table
    shared = select(share.c.reference_id).where(
        share.c.reference_doctype == doctype.name,
        share.c.user == user,
        share.c.permission.in_(levels),
    )
    roots = set((await grunt.get_session().execute(shared)).scalars().all())
    if not roots:
        return None
    return In("name", tuple(sorted(await expand_tree_values(doctype.name, roots))))
