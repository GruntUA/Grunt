"""Controller for the ``NotificationLog`` DocType - one item in a user's bell."""

from grunt.document.base import Document


class NotificationLog(Document):
    """DocType controller for NotificationLog."""

    # "user" field: read it as self.data["user"] - self.user is the session user.
    subject: str | None
    message: str | None
    ref_doctype: str | None
    doc_id: str | None
    is_read: bool | None
    notification: str | None
