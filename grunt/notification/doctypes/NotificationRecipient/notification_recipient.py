"""Controller for the ``NotificationRecipient`` DocType - one "who" row of a notification."""

from grunt.document.base import Document


class NotificationRecipient(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    kind: str | None = None  # Who
    role: str | None = None  # Role
    user_group: str | None = None  # User group
    user: str | None = None  # User
    field: str | None = None  # Field
    email: str | None = None  # Email
    condition: str | None = None  # Condition

    # end: auto-generated types

    """DocType controller for NotificationRecipient."""
