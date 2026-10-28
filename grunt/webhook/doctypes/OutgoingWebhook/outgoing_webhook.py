"""Controller for the ``OutgoingWebhook`` DocType."""

from grunt.document.base import Document


class OutgoingWebhook(Document):
    """DocType controller for OutgoingWebhook."""

    doctype_name: str | None
    event: str | None
    url: str | None
    secret: str | None
    headers: str | None
    condition: str | None
    timeout: int | None
    is_enabled: bool | None
