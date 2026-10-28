"""Controller for the ``DocTypeAction`` DocType."""

from grunt.document.base import Document


class DocTypeAction(Document):
    """DocType controller for DocTypeAction."""

    action: str | None
    label: str | None
    group: str | None
    variant: str | None
    hidden: bool | None
    condition: str | None
