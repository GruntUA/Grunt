"""Controller for the ``EmailTemplate`` DocType."""

from grunt.document.base import Document


class EmailTemplate(Document):
    """DocType controller for EmailTemplate."""

    label: str | None
    is_active: bool | None
    subject: str | None
    body: str | None
    body_html: str | None
    is_standard: bool | None
    app: str | None
    description: str | None
