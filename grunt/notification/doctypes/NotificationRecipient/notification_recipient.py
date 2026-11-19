"""Controller for the ``NotificationRecipient`` DocType - one "who" row of a notification."""

from grunt.document.base import Document


class NotificationRecipient(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    # "user" field: read it as self.data["user"] - self.user is taken by the controller.
    kind: str  # Who
    role: str | None  # Role
    user_group: str | None  # User group
    field: str | None  # Field
    email: str | None  # Email
    condition: str | None  # Condition

    # end: auto-generated types

    """DocType controller for NotificationRecipient."""

    kind: str
    role: str | None
    # "user" field: read it as self.data["user"] - self.user is the session user.
    field: str | None
    email: str | None
    condition: str | None
