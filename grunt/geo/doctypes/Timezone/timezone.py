"""Controller for the ``Timezone`` DocType."""

from grunt.document.base import Document


class Timezone(Document):
    """DocType controller for Timezone."""

    iana_id: str | None
    label: str | None
    offset_minutes: int | None
    is_dst_observed: bool | None
    is_active: bool | None
