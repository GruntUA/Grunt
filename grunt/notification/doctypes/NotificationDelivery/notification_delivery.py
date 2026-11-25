"""Controller for the ``NotificationDelivery`` DocType - the delivery log."""

from grunt.document.base import Document


class NotificationDelivery(Document):
    """DocType controller for NotificationDelivery."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    recipient: str  # Recipient
    channel: str  # Channel
    status: str  # Status
    subject: str | None = None  # Subject
    reason: str | None = None  # Reason
    notification: str | None = None  # Notification
    event_key: str | None = None  # Event
    ref_doctype: str | None = None  # Document type
    doc_id: str | None = None  # Document ID
    notification_log: str | None = None  # Notification Log
    email_queue: str | None = None  # Email queue
    email_message: str | None = None  # Email message

    # end: auto-generated types
