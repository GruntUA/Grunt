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
    the document-level check that follows still requires a share on that doc.
    """
    import grunt
    from grunt.local import _session_ctx

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
        filters["reference_id"] = str(doc_name)
    return bool(await grunt.db.exists("SharedWith", filters))


async def shared_names_clause(table: Table, user: User, doctype: str) -> ColumnElement[bool] | None:
    """``name IN (<docs of doctype shared with user>)`` for list queries."""
    import grunt

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
    return table.c.name.in_(shared)
