"""Controller for the ``IncomingWebhook`` DocType."""

from grunt.document.base import Document


class IncomingWebhook(Document):
    """DocType controller for IncomingWebhook."""

    label: str | None
    slug: str | None
    secret: str | None
    signature_header: str | None
    signature_type: str | None
    action: str | None
    server_script: str | None
    target_doctype: str | None
    field_mapping: str | None
    is_enabled: bool | None
