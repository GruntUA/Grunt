"""Controller for the ``IncomingWebhookLog`` DocType."""

from grunt.document.base import Document


class IncomingWebhookLog(Document):
    """DocType controller for IncomingWebhookLog."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    webhook: str | None = None  # Webhook
    slug: str | None = None  # Slug
    status: str | None = None  # Status
    action_taken: str | None = None  # Action taken
    duration_ms: int | None = None  # Time (ms)
    request_headers: str | None = None  # Request headers
    payload: str | None = None  # Request body
    error: str | None = None  # Error

    # end: auto-generated types
