"""Controller for the ``Bookmark`` DocType."""

from grunt.document.base import Document


class Bookmark(Document):
    """DocType controller for Bookmark."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    reference_doctype: str  # Document type
    reference_id: str  # Document ID
    title: str | None = None  # Name

    # end: auto-generated types
