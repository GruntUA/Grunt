"""Permission checking API.

Example:
    from grunt import can_read, can_write, can_submit, get_current_user

    # Check permissions
    if not await can_read("Contract", contract_id):
        throw("You don't have permission to read this contract")

    if not await can_write("Invoice", invoice_id):
        throw("Read-only access")

    user = await get_current_user()
    if "Admin" not in user.roles:
        throw("Admin access required")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.api.context import get_user
from grunt.app import grunt

if TYPE_CHECKING:
    from grunt.core.auth.models import GruntUser


async def get_current_user() -> GruntUser:
    """Get the current user from context.

    Returns:
        GruntUser with email, full_name, roles, is_superadmin
    """
    return get_user()


async def _check_doctype_permission(doctype: str, permission: str) -> bool:
    """Check if user has a specific permission for a DocType.

    Args:
        doctype: e.g., "Invoice"
        permission: e.g., "read", "write", "create", "delete", "submit"

    Returns:
        True if user has the permission
    """
    user = get_user()

    if user.is_superadmin:
        return True

    if user.email == "system":
        return True

    user_roles = user.roles or []
    if not user_roles:
        return False

    try:
        rows = await grunt.db.get_all(
            "DocTypePermission",
            filters={"doctype_name": doctype},
            limit=1000,
        )
        return any(row.get("role") in user_roles and row.get(permission) for row in rows)

    except Exception:
        return False


async def can_read(doctype: str, doc_id: str) -> bool:
    """Check if current user can read a document.

    Args:
        doctype: e.g., "Invoice"
        doc_id: Document ID

    Returns:
        True if user has read permission
    """
    return await _check_doctype_permission(doctype, "read")


async def can_write(doctype: str, doc_id: str) -> bool:
    """Check if current user can write to a document.

    Args:
        doctype: e.g., "Invoice"
        doc_id: Document ID

    Returns:
        True if user has write permission
    """
    return await _check_doctype_permission(doctype, "write")


async def can_submit(doctype: str, doc_id: str) -> bool:
    """Check if current user can submit a document.

    Args:
        doctype: e.g., "Invoice"
        doc_id: Document ID

    Returns:
        True if user has submit permission
    """
    return await _check_doctype_permission(doctype, "submit")


async def can_delete(doctype: str, doc_id: str) -> bool:
    """Check if current user can delete a document.

    Args:
        doctype: e.g., "Invoice"
        doc_id: Document ID

    Returns:
        True if user has delete permission
    """
    return await _check_doctype_permission(doctype, "delete")


async def can_create(doctype: str) -> bool:
    """Check if current user can create a new document.

    Args:
        doctype: e.g., "Invoice"

    Returns:
        True if user has create permission
    """
    return await _check_doctype_permission(doctype, "create")
