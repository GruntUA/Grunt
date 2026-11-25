"""Controller for the ``Timezone`` DocType."""

from grunt.document.base import Document


class Timezone(Document):
    """DocType controller for Timezone."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    iana_id: str  # IANA identifier
    label: str | None = None  # Display name
    offset_minutes: int | None = None  # Offset (minutes)
    is_dst_observed: bool | None = None  # Daylight saving time
    is_active: bool | None = None  # Active

    # end: auto-generated types
