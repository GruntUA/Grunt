"""Controller for the ``IncomingWebhookLog`` DocType."""

from grunt.document.base import Document


class IncomingWebhookLog(Document):
    """DocType controller for IncomingWebhookLog."""

    webhook: str | None
    slug: str | None
    status: str | None
    action_taken: str | None
    duration_ms: int | None
    request_headers: str | None
    payload: str | None
    error: str | None
