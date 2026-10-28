"""Controller for the ``Bookmark`` DocType."""

from grunt.document.base import Document


class Bookmark(Document):
    """DocType controller for Bookmark."""

    reference_doctype: str | None
    reference_id: str | None
    title: str | None
