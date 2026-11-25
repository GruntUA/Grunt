"""Controller for the ``NotificationLog`` DocType - one item in a user's bell."""

from grunt.document.base import Document


class NotificationLog(Document):
    """DocType controller for NotificationLog."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    user: str  # User
    subject: str  # Subject
    message: str  # Message
    ref_doctype: str | None = None  # Document type
    doc_id: str | None = None  # Document ID
    is_read: bool | None = None  # Read
    notification: str | None = None  # Notification

    # end: auto-generated types
