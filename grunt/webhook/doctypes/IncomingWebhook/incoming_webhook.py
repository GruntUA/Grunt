"""Controller for the ``IncomingWebhook`` DocType."""

from grunt.document.base import Document


class IncomingWebhook(Document):
    """DocType controller for IncomingWebhook."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    label: str  # Name
    slug: str  # URL path (slug)
    secret: str | None = None  # Secret (HMAC)
    signature_header: str | None = None  # Signature header
    signature_type: str | None = None  # Signature algorithm
    action: str | None = None  # Action
    server_script: str | None = None  # Server Script
    target_doctype: str | None = None  # Document type
    field_mapping: str | None = None  # Field mapping (JSON)
    is_enabled: bool | None = None  # Active

    # end: auto-generated types
