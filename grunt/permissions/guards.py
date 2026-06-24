"""Shared permission guards for the facade and API layer.

Module-level helpers (previously methods on ``PermissionAPI``) so callers can
import and call them directly instead of routing through sibling-mixin ``self``
calls. ``PermissionAPI`` keeps thin method wrappers around these for backward
compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.context import require_session, require_user
from grunt.metadata.registry import doctype_registry
from grunt.permissions.types import WriteAction

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

    dt = await doctype_registry.get(doctype)
    user = require_user()
    await permission_checker.require(user, dt, "read")
    hidden_fields = permission_checker.hidden_fields(user, dt)
    return dt, user, hidden_fields


async def write_guard(doctype: str, action: WriteAction) -> tuple[Any, User, AsyncSession]:
    """Shared pre-flight for every write operation at the high-level layer.

    Returns ``(dt, user, session)``. Raises ``403`` when the user has no
    permission for *action* (``"create"``, ``"write"``, or ``"delete"``).
    """
    from grunt.permissions.rbac import permission_checker

    dt = await doctype_registry.get(doctype)
    user = require_user()
    await permission_checker.require(user, dt, action)
    return dt, user, require_session()
