"""Controller for the ``NamingSeries`` DocType."""

from grunt.document.base import Document


class NamingSeries(Document):
    """DocType controller for NamingSeries."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    prefix: str  # Prefix
    current: int | None = None  # Current value

    # end: auto-generated types
