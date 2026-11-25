"""Controller for the ``Milestone`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class Milestone(Document):
    """DocType controller for Milestone."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str | None = None  # Document type
    ref_name: str | None = None  # Document
    track_field: str | None = None  # Field
    value: str | None = None  # Value
    previous_value: str | None = None  # Previous value
    entered_at: datetime | None = None  # Entered
    left_at: datetime | None = None  # Left
    duration_hours: float | None = None  # Hours
    entered_by: str | None = None  # Changed by
    approximate: bool | None = None  # Approximate

    # end: auto-generated types
