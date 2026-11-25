"""Controller for the ``ViewLog`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class ViewLog(Document):
    """DocType controller for ViewLog."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str  # Document type
    doc_id: str  # Document ID
    viewed_by: str  # Viewed by
    viewed_at: datetime  # Viewed at

    # end: auto-generated types
