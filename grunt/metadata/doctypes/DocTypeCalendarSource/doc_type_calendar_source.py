"""Controller for the ``DocTypeCalendarSource`` DocType."""

from grunt.document.base import Document


class DocTypeCalendarSource(Document):
    """DocType controller for DocTypeCalendarSource."""

    ref_doctype: str | None
    date_field: str | None
    end_date_field: str | None
    label_field: str | None
    color: str | None
    event_type: str | None
    recurring: bool | None
    show_age: bool | None
    filters: dict | None
