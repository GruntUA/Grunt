"""Controller for the ``PushSubscription`` DocType."""

from grunt.document.base import Document


class PushSubscription(Document):
    """DocType controller for PushSubscription."""

    user: str
    endpoint: str | None
    p256dh: str | None
    auth: str | None
    user_agent: str | None
