"""Controller for the ``EmailQueue`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class EmailQueue(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    sender: str | None  # Sender
    recipient: str | None  # Recipient
    cc: str | None  # Cc
    bcc: str | None  # Bcc
    reply_to: str | None  # Reply-To
    subject: str | None  # Subject
    content: str | None  # Content
    text_content: str | None  # Text version
    is_html: bool | None  # HTML
    status: str | None  # Status
    priority: str | None  # Priority
    send_after: datetime | None  # Send after
    retry: int | None  # Attempts failed
    unsubscribe_url: str | None  # Unsubscribe link
    error_message: str | None  # Error
    email_account: str | None  # Account
    attachments: dict | None  # Attachments
    message_id: str | None  # Message-ID
    in_reply_to: str | None  # In-Reply-To
    message_references: str | None  # References
    ref_doctype: str | None  # Source — type
    ref_name: str | None  # Source — record

    # end: auto-generated types

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
