"""Controller for the ``DocTypeCalendarSource`` DocType."""

from typing import Any

from grunt.document.base import Document


class DocTypeCalendarSource(Document):
    """DocType controller for DocTypeCalendarSource."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str  # DocType
    date_field: str  # Date field
    end_date_field: str | None = None  # End date field
    label_field: str | None = None  # Label field
    color: str | None = None  # Color
    event_type: str | None = None  # Event type
    recurring: bool | None = None  # Yearly
    show_age: bool | None = None  # Show age
    filters: Any | None = None  # Filters (JSON)

    # end: auto-generated types
