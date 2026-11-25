"""Controller for the ``DocTypeStatusIndicator`` DocType."""

from grunt.document.base import Document


class DocTypeStatusIndicator(Document):
    """DocType controller for DocTypeStatusIndicator."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    value: str  # Field value
    color: str | None = None  # Color
    icon: str | None = None  # Icon
    label: str | None = None  # Label

    # end: auto-generated types
