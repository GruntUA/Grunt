"""Controller for the ``EmailQueue`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class EmailQueue(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    sender: str | None = None  # Sender
    recipient: str | None = None  # Recipient
    cc: str | None = None  # Cc
    bcc: str | None = None  # Bcc
    reply_to: str | None = None  # Reply-To
    subject: str | None = None  # Subject
    content: str | None = None  # Content
    text_content: str | None = None  # Text version
    is_html: bool | None = None  # HTML
    status: str | None = None  # Status
    priority: str | None = None  # Priority
    send_after: datetime | None = None  # Send after
    retry: int | None = None  # Attempts failed
    unsubscribe_url: str | None = None  # Unsubscribe link
    error_message: str | None = None  # Error
    email_account: str | None = None  # Account
    attachments: dict | None = None  # Attachments
    message_id: str | None = None  # Message-ID
    in_reply_to: str | None = None  # In-Reply-To
    message_references: str | None = None  # References
    ref_doctype: str | None = None  # Source — type
    ref_name: str | None = None  # Source — record

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
