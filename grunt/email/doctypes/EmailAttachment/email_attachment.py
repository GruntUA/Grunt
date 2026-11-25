"""Controller for the ``EmailAttachment`` DocType."""

from grunt.document.base import Document


class EmailAttachment(Document):
    """DocType controller for EmailAttachment."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    filename: str | None = None  # File name
    file: str | None = None  # File
    size: int | None = None  # Size, B
    mimetype: str | None = None  # Type

    # end: auto-generated types
