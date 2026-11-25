"""Controller for the ``PushSubscription`` DocType."""

from grunt.document.base import Document


class PushSubscription(Document):
    """DocType controller for PushSubscription."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    user: str  # User
    endpoint: str  # Endpoint
    p256dh: str  # p256dh key
    auth: str  # Auth key
    user_agent: str | None = None  # User Agent

    # end: auto-generated types
