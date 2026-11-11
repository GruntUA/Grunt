"""Shared permission guards for the facade and API layer.

Module-level helpers (previously methods on ``PermissionAPI``) so callers can
import and call them directly instead of routing through sibling-mixin ``self``
calls. ``PermissionAPI`` keeps thin method wrappers around these for backward
compatibility.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.errors import not_found
from grunt.i18n import _
from grunt.local import require_session, require_session_user
from grunt.metadata.registry import doctype_registry
from grunt.permissions.rbac import permission_checker
from grunt.permissions.types import PermissionAction, WriteAction
lazy from grunt.store.lookup import store_for


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


async def read_guard(doctype: str) -> tuple[Any, str, frozenset[str]]:
    """Shared pre-flight for every read operation at the high-level layer.

    Returns ``(dt, user email, hidden_fields)``. Raises ``403`` when the user has no
    *read* permission on the DocType.
    """
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = require_session_user()
    await permission_checker.require(dt, "read", user=user)
    hidden_fields = await permission_checker.hidden_fields(dt, user=user)
    return dt, user, hidden_fields


async def doctype_guard(doctype: str | None, action: PermissionAction) -> Any:
    """The DocType's meta, when the current user may *action* on it (DocType
    level - no document). ``404`` for an unknown DocType, ``403`` without it."""
    dt = await doctype_registry.get_meta(doctype) if doctype else None
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    await permission_checker.require(dt, action, user=require_session_user())
    return dt


async def doc_guard(doctype: str, doc_id: str, action: PermissionAction = "read") -> None:
    """Verify the current user may act on *doc_id*, without loading the document.

    Callers that only need the permission check (the document itself is
    discarded) should use this instead of ``grunt.get_doc`` - it fetches the
    bare row (no child tables, multi-link, or ``read_formula`` fields) just to
    evaluate row-level ``match``/User Permission rules. Raises ``404`` when
    the document does not exist, ``403`` when the action is not permitted.
    """
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = require_session_user()

    doc = await store_for(dt).get(dt.name if dt.is_singleton else doc_id, expand=[])
    if doc is None:
        raise not_found(_("Document “%(name)s” not found") % {"name": doc_id})
    await permission_checker.require(dt, action, doc, user=user)


async def write_guard(doctype: str, action: WriteAction) -> tuple[Any, str, AsyncSession]:
    """Shared pre-flight for every write operation at the high-level layer.

    Returns ``(dt, user email, session)``. Raises ``403`` when the user has no
    permission for *action* (``"create"``, ``"write"``, or ``"delete"``).
    """
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = require_session_user()
    await permission_checker.require(dt, action, user=user)
    return dt, user, require_session()
