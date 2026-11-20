"""EmailUnsubscribe - an address that turned off notification emails
(:mod:`grunt.email.unsubscribe`)."""

from grunt.document.base import Document


class EmailUnsubscribe(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    email: str  # Email
    notification: str | None  # Notification

    # end: auto-generated types

    async def validate(self) -> None:
        self.data["email"] = (self.get("email") or "").strip().lower()
