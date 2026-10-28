"""Controller for the ``Notification`` DocType."""

from grunt.document.base import Document


class Notification(Document):
    """DocType controller for Notification."""

    # "user" field: read it as self.data["user"] - self.user is the session user.
    subject: str | None
    message: str | None
    ref_doctype: str | None
    doc_id: str | None
    is_read: bool | None
    notification_rule: str | None
