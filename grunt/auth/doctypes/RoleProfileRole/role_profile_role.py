"""RoleProfileRole DocType controller - child table of ``RoleProfile.roles``."""

from grunt.document.base import Document


class RoleProfileRole(Document):
    """DocType controller for RoleProfileRole (a child row of ``RoleProfile.roles``)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    role_name: str  # Role
    scope_doctype: str | None = None  # Scope
    scope_value: str | None = None  # Scope value

    # end: auto-generated types
