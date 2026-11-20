"""Controller for the ``EmailQueue`` DocType."""

from grunt.document.base import Document


class EmailQueue(Document):
    """DocType controller for EmailQueue."""

    sender: str | None
    recipient: str | None
    cc: str | None
    bcc: str | None
    reply_to: str | None
    subject: str | None
    content: str | None
    text_content: str | None
    is_html: bool | None
    status: str | None
    error_message: str | None
    email_account: str | None
    attachments: dict | None
    message_id: str | None
    in_reply_to: str | None
    message_references: str | None
    ref_doctype: str | None
    ref_name: str | None
