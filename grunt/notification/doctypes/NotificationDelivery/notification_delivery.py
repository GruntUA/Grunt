"""Controller for the ``NotificationDelivery`` DocType - the delivery log."""

from grunt.document.base import Document


class NotificationDelivery(Document):
    """DocType controller for NotificationDelivery."""

    recipient: str
    channel: str
    status: str
    subject: str | None
    reason: str | None
    notification: str | None
    event_key: str | None
    ref_doctype: str | None
    doc_id: str | None
    notification_log: str | None
    email_queue: str | None
    email_message: str | None
