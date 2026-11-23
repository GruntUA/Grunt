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
        self.data["email"] = (self.get("email") or "").strip().lower()
        self.data["notification"] = self.get("notification") or None
        self.data["channel"] = self.get("channel") or None
