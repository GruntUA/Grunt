"""Controller for the ``NamingSeries`` DocType."""

from grunt.document.base import Document


class NamingSeries(Document):
    """DocType controller for NamingSeries."""

    prefix: str | None
    current: int | None
