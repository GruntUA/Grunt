"""Controller for the ``EmailMessage`` DocType."""

from datetime import datetime
from typing import Any

from grunt.document.base import Document


class EmailMessage(Document):
    """DocType controller for EmailMessage."""

    direction: str | None
    message_date: datetime | None
    status: str | None
    email_account: str | None
    subject: str | None
    sender: str | None
    recipients: str | None
    cc: str | None
    body_html: str | None
    body_text: str | None
    has_attachments: bool | None
    attachments: list[dict[str, Any]]  # Table: EmailAttachment
    error_message: str | None
    delivered_at: datetime | None
    read_at: datetime | None
    request_receipt: bool | None
    delivery_detail: str | None
    ref_doctype: str | None
    ref_name: str | None
    message_id: str | None
    is_read: bool | None
