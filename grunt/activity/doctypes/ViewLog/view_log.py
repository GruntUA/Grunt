"""Controller for the ``ViewLog`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class ViewLog(Document):
    """DocType controller for ViewLog."""

    ref_doctype: str | None
    doc_id: str | None
    viewed_by: str | None
    viewed_at: datetime | None
