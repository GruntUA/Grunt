"""Controller for the ``WebhookLog`` DocType."""

from grunt.document.base import Document


class WebhookLog(Document):
    """DocType controller for WebhookLog."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    webhook: str | None = None  # Webhook
    event: str | None = None  # Event
    url: str | None = None  # URL
    status_code: int | None = None  # HTTP status
    success: bool | None = None  # Success
    duration_ms: int | None = None  # Time (ms)
    response_body: str | None = None  # Response
    error: str | None = None  # Error
    is_test: bool | None = None  # Test

    # end: auto-generated types
