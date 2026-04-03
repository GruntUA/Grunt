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

from sqlalchemy import select

from grunt.api.context import get_session, get_user
from grunt.core.auth.models import GruntUser
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry


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

    # Superadmin bypass
    if user.is_superadmin:
        return True

    # System user always allowed
    if user.email == "system":
        return True

    # Get user roles
    user_roles = user.roles or []
    if not user_roles:
        return False

    try:
        session = get_session()

        # Get DocTypePermission table
        doctype_perm_def = doctype_registry.get_doctype("DocTypePermission")
        if not doctype_perm_def:
            # DocTypePermission not defined, allow all
            return True

        doctype_perm_table = compile_doctype_to_table(doctype_perm_def)

        # Query: find permission for this doctype + user roles
        stmt = select(doctype_perm_table).where(
            doctype_perm_table.c.doctype_name == doctype,
            doctype_perm_table.c.role.in_(user_roles),
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        # Check if any role has this permission
        for row in rows:
            # Get the permission value (read, write, create, delete, submit, etc.)
            perm_value = getattr(row, permission, False)
            if perm_value:
                return True

        return False

    except Exception:
        # On error, default to False (deny access)
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

