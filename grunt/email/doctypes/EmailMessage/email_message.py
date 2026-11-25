"""Controller for the ``EmailMessage`` DocType."""

from datetime import datetime

from grunt.document.base import Document
from grunt.email.doctypes.EmailAttachment.email_attachment import EmailAttachment


class EmailMessage(Document):
    """DocType controller for EmailMessage."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    direction: str | None = None  # Direction
    message_date: datetime | None = None  # Date / time
    status: str | None = None  # Status
    email_account: str | None = None  # Account
    subject: str | None = None  # Subject
    sender: str | None = None  # From
    recipients: str | None = None  # To
    cc: str | None = None  # Cc
    body_html: str | None = None  # HTML
    body_text: str | None = None  # Text
    has_attachments: bool | None = None  # Has attachments
    error_message: str | None = None  # Error text
    delivered_at: datetime | None = None  # Delivered at
    read_at: datetime | None = None  # Read by recipient at
    request_receipt: bool | None = None  # Read receipt requested
    delivery_detail: str | None = None  # Delivery details / diagnostics
    ref_doctype: str | None = None  # Source — type
    ref_name: str | None = None  # Source — record
    message_id: str | None = None  # Message-ID
    in_reply_to: str | None = None  # In-Reply-To
    message_references: str | None = None  # References
    unreplied_checked: bool | None = None  # Checked for a reply
    is_auto_reply: bool | None = None  # Auto-reply
    is_read: bool | None = None  # Read
    attachments: list[EmailAttachment] = []  # Attachments

    # end: auto-generated types
