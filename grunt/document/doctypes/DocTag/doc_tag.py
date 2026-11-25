"""Controller for the ``DocTag`` DocType."""

from grunt.document.base import Document


class DocTag(Document):
    """DocType controller for DocTag."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    reference_doctype: str  # Document type
    reference_id: str  # Document ID
    tag: str  # Tag

    # end: auto-generated types
