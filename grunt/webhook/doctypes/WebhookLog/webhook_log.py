"""Controller for the ``WebhookLog`` DocType."""

from grunt.document.base import Document


class WebhookLog(Document):
    """DocType controller for WebhookLog."""

    webhook: str | None
    event: str | None
    url: str | None
    status_code: int | None
    success: bool | None
    duration_ms: int | None
    response_body: str | None
    error: str | None
    is_test: bool | None
