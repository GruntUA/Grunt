"""Controller for the ``NotificationChannel`` DocType - a channel of a notification."""

from grunt.document.base import Document


class NotificationChannel(Document):
    """DocType controller for NotificationChannel."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    channel: str  # Channel
    webhook: str | None = None  # Webhook
    subject: str | None = None  # Subject
    message: str | None = None  # Message

    # end: auto-generated types
