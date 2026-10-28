"""Controller for the ``EmailQueue`` DocType."""

from grunt.document.base import Document


class EmailQueue(Document):
    """DocType controller for EmailQueue."""

    sender: str | None
    recipient: str | None
    subject: str | None
    content: str | None
    text_content: str | None
    is_html: bool | None
    status: str | None
    error_message: str | None
    email_account: str | None
    attachments: dict | None
