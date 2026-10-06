"""Document shares - a ``SharedWith`` row grants one user access to one document.

``permission = "Read"`` grants read (and select); ``"Write"`` also grants write.
Shares only *add* access on top of role permissions (see
:meth:`grunt.permissions.rbac.PermissionChecker.check` and
:func:`grunt.permissions.query.apply_permission_filter`); they never grant
create or delete, and never apply to a different document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

import grunt
from grunt.local import _session_ctx

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, Table

    from grunt.auth.doctypes.User.user import User

# action -> share levels that grant it
_LEVELS: dict[str, tuple[str, ...]] = {
    "read": ("Read", "Write"),
    "select": ("Read", "Write"),
    "write": ("Write",),
}

SHAREABLE_ACTIONS = frozenset(_LEVELS)


async def has_share(user: User, doctype: str, action: str, doc_name: str | None = None) -> bool:
    """True if *user* holds a share granting *action* on *doc_name*.

    ``doc_name=None`` asks about the DocType as a whole - any share on any of
    its documents - which is what the doctype-level pre-flight guards need;
    the document-level check that follows still requires a share on that doc
    (or, with ``shares_cover_subtree``, on one of its tree ancestors).
    """
    levels = _LEVELS.get(action)
    # No bound session: a pure in-memory check (unit tests, startup) - there is
    # no DB to hold shares, so roles alone decide.
    if not levels or not user.email or _session_ctx.get() is None:
        return False
    filters: dict[str, object] = {
        "reference_doctype": doctype,
        "user": user.email,
        "permission__in": list(levels),
    }
    if doc_name is not None:
        filters["reference_id__in"] = await _with_ancestors(doctype, str(doc_name))
    return bool(await grunt.db.exists("SharedWith", filters))


async def _subtree_parent_field(doctype: str) -> str | None:
    meta = await grunt.get_meta(doctype)
    if meta is None or not getattr(meta, "shares_cover_subtree", False):
        return None
    return getattr(meta, "tree_parent_field", None) if getattr(meta, "is_tree", False) else None


async def _with_ancestors(doctype: str, name: str) -> list[str]:
    """*name* plus, when shares cover subtrees, every ancestor of it."""
    parent_field = await _subtree_parent_field(doctype)
    out = [name]
    while parent_field:
        parent = await grunt.db.get_value(doctype, out[-1], parent_field)
        if not parent or parent in out:
            break
        out.append(parent)
    return out


async def shared_names_clause(table: Table, user: User, doctype: str) -> ColumnElement[bool] | None:
    """``name IN (<docs of doctype shared with user>)`` for list queries."""
    if not user.email or "name" not in table.c:
        return None
    meta = await grunt.get_meta("SharedWith")
    if meta is None:
        return None
    share = meta.table
    shared = select(share.c.reference_id).where(
        share.c.reference_doctype == doctype,
        share.c.user == user.email,
    )
    if await _subtree_parent_field(doctype) is None:
        return table.c.name.in_(shared)

    from grunt.permissions.user_permissions import expand_tree_values

    roots = set((await grunt.get_session().execute(shared)).scalars().all())
    return table.c.name.in_(await expand_tree_values(doctype, roots)) if roots else None
