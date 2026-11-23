"""NotificationPreference - a notification a person turned off
(:mod:`grunt.notification.preferences`)."""

from grunt.document.base import Document


class NotificationPreference(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    email: str  # Email
    notification: str | None = None  # Notification
    channel: str | None = None  # Channel

    # end: auto-generated types

    async def validate(self) -> None:
        self.email = (self.email or "").strip().lower()
        self.notification = self.notification or None
        self.channel = self.channel or None
