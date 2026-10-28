"""Controller for the ``DocTypeStatusIndicator`` DocType."""

from grunt.document.base import Document


class DocTypeStatusIndicator(Document):
    """DocType controller for DocTypeStatusIndicator."""

    value: str | None
    color: str | None
    icon: str | None
    label: str | None
