"""ApiKeyRole DocType controller - child table of ``ApiKey.roles``."""

from grunt.document.base import Document


class ApiKeyRole(Document):
    """DocType controller for ApiKeyRole (a child row of ``ApiKey.roles``)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    role_name: str  # Role

    # end: auto-generated types
