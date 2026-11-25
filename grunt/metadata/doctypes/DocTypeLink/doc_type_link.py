"""Controller for the ``DocTypeLink`` DocType."""

from grunt.document.base import Document


class DocTypeLink(Document):
    """DocType controller for DocTypeLink."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    link_doctype: str  # Related DocType
    link_fieldname: str  # Link field
    group: str | None = None  # Group
    label: str | None = None  # Label
    hidden: bool | None = None  # Hidden
    parent_doctype: str | None = None  # Child DocType
    table_fieldname: str | None = None  # Table field

    # end: auto-generated types
