"""Controller for the ``Region`` DocType."""

from grunt.document.base import Document


class Region(Document):
    """DocType controller for Region."""

    title: str | None
    title_uk: str | None
    country: str | None
    code: str | None
    region_type: str | None
    is_active: bool | None
