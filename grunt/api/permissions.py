"""User/permission lookup API.

Permission checks themselves live on the facade as ``grunt.has_permission``
(``grunt/app/permission_api.py``) — this module only adds ``get_current_user``.

Example:
    from grunt import get_current_user

    # DocType-level check
    if not await grunt.has_permission("Invoice", "write"):
        throw("Read-only access")

    # Document-level check — also evaluates the matching DocPermission's
    # match expression (e.g. "owner == user") against this document
    if not await grunt.has_permission("Contract", "read", contract_id):
        throw("You don't have permission to read this contract")

    user = await get_current_user()
    if "Admin" not in user.roles:
        throw("Admin access required")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.api.context import get_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


async def get_current_user() -> User:
    """Get the current user from context.

    Returns:
        User with email, full_name, roles, is_superadmin
    """
    return get_user()
