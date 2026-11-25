"""UserRoleProfile DocType controller - child table of ``User.role_profiles``."""

from grunt.document.base import Document


class UserRoleProfile(Document):
    """DocType controller for UserRoleProfile (a child row of ``User.role_profiles``)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    role_profile: str  # Role profile

    # end: auto-generated types
