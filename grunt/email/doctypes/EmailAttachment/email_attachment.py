"""Controller for the ``EmailAttachment`` DocType."""

from grunt.document.base import Document


class EmailAttachment(Document):
    """DocType controller for EmailAttachment."""

    filename: str | None
    file: str | None
    size: int | None
    mimetype: str | None
