"""Controller for the ``NotificationChannel`` DocType - a channel of a notification."""

from grunt.document.base import Document


class NotificationChannel(Document):
    """DocType controller for NotificationChannel."""

    channel: str
    subject: str | None
    message: str | None
