"""Controller for the ``NotificationRecipient`` DocType - one "who" row of a notification."""

from grunt.document.base import Document


class NotificationRecipient(Document):
    """DocType controller for NotificationRecipient."""

    kind: str
    role: str | None
    # "user" field: read it as self.data["user"] - self.user is the session user.
    field: str | None
    email: str | None
    condition: str | None
