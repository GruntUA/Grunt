"""Controller for the ``DocLink`` DocType."""

from grunt.document.base import Document


class DocLink(Document):
    """DocType controller for DocLink."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    source_doctype: str  # Source type
    source_id: str  # Source ID
    target_doctype: str  # Target type
    target_id: str  # Target ID
    link_fieldname: str  # Link field

    # end: auto-generated types
