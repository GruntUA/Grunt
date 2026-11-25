"""Controller for the ``Region`` DocType."""

from grunt.document.base import Document


class Region(Document):
    """DocType controller for Region."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Name
    title_uk: str | None = None  # Name (Ukrainian)
    country: str  # Country
    code: str | None = None  # ISO 3166-2 code
    region_type: str | None = None  # Type
    is_active: bool | None = None  # Active

    # end: auto-generated types
