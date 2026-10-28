"""Controller for the ``Milestone`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class Milestone(Document):
    """DocType controller for Milestone."""

    ref_doctype: str | None
    ref_name: str | None
    track_field: str | None
    value: str | None
    previous_value: str | None
    entered_at: datetime | None
    left_at: datetime | None
    duration_hours: float | None
    entered_by: str | None
    approximate: bool | None
