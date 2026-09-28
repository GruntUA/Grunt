"""Shared permission guards for the facade and API layer.

Module-level helpers (previously methods on ``PermissionAPI``) so callers can
import and call them directly instead of routing through sibling-mixin ``self``
calls. ``PermissionAPI`` keeps thin method wrappers around these for backward
compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grunt
from grunt import _
from grunt.errors import not_found
from grunt.local import require_user
from grunt.permissions.types import PermissionAction, WriteAction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.user import User


def apply_hidden_fields_to_doc(
    doc: dict[str, Any],
    hidden_fields: frozenset[str],
) -> dict[str, Any]:
    """Strip permission-hidden fields from a single document dict, in place."""
    if not hidden_fields:
        return doc
    for field in hidden_fields:
        doc.pop(field, None)
    return doc


def apply_hidden_fields_to_rows(
    rows: list[dict[str, Any]],
    hidden_fields: frozenset[str],
) -> list[dict[str, Any]]:
    """Strip permission-hidden fields from a list of row dicts, in place."""
    if not hidden_fields:
        return rows
    for row in rows:
        for field in hidden_fields:
            row.pop(field, None)
    return rows


async def read_guard(doctype: str) -> tuple[Any, User, frozenset[str]]:
    """Shared pre-flight for every read operation at the high-level layer.

    Returns ``(dt, user, hidden_fields)``. Raises ``403`` when the user has no
    *read* permission on the DocType.
    """
    from grunt.permissions.rbac import permission_checker

    dt = await grunt.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = require_user()
    await permission_checker.require(user, dt, "read")
    hidden_fields = permission_checker.hidden_fields(user, dt)
    return dt, user, hidden_fields


async def doc_guard(doctype: str, doc_id: str, action: PermissionAction = "read") -> None:
    """Verify the current user may act on *doc_id*, without loading the document.

    Callers that only need the permission check (the document itself is
    discarded) should use this instead of ``grunt.get_doc`` — it fetches the
    bare row (no child tables, multi-link, or ``read_formula`` fields) just to
    evaluate row-level ``match``/User Permission rules. Raises ``404`` when
    the document does not exist, ``403`` when the action is not permitted.
    """
    from grunt.document.virtual import is_virtual_routed
    from grunt.permissions.rbac import permission_checker

    dt = await grunt.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = require_user()
    if is_virtual_routed(dt, doctype):
        # No table to look the row up in — the DocType-level check is all there is.
        await permission_checker.require(user, dt, action)
        return
    lookup_id = dt.name if dt.is_singleton else doc_id
    doc = await grunt.db.get_value(doctype, lookup_id, "*")
    if doc is None:
        raise not_found(_("Document “%(name)s” not found") % {"name": doc_id})
    await permission_checker.require(user, dt, action, doc)


async def write_guard(doctype: str, action: WriteAction) -> tuple[Any, User, AsyncSession]:
    """Shared pre-flight for every write operation at the high-level layer.

    Returns ``(dt, user, session)``. Raises ``403`` when the user has no
    permission for *action* (``"create"``, ``"write"``, or ``"delete"``).
    """
    from grunt.permissions.rbac import permission_checker

    dt = await grunt.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = require_user()
    await permission_checker.require(user, dt, action)
    return dt, user, grunt.get_session()
