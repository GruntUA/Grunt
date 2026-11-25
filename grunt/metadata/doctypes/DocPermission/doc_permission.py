"""Controller for the ``DocPermission`` DocType."""

from grunt.document.base import Document


class DocPermission(Document):
    """DocType controller for DocPermission."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    role: str  # Role
    actions: list[str] | None = None  # Actions
    match: str | None = None  # Row condition
    hidden_fields: str | None = None  # Hidden fields (comma-separated)
    readonly_fields: str | None = None  # Read-only fields (comma-separated)

    # end: auto-generated types
