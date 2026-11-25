"""Controller for the ``OutgoingWebhook`` DocType."""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _


class OutgoingWebhook(Document):
    """DocType controller for OutgoingWebhook."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    doctype_name: str | None = None  # Document type
    event: str  # Event
    url: str  # Webhook URL
    secret: str | None = None  # Secret (HMAC)
    headers: str | None = None  # Headers (JSON)
    condition: str | None = None  # Condition (Python)
    timeout: int | None = None  # Timeout (sec)
    is_enabled: bool | None = None  # Active

    # end: auto-generated types

    async def validate(self) -> None:
        # The document type matters to document events; a webhook only notification
        # rules post to ("notification") has none.
        if self.event != "notification" and not self.doctype_name:
            throw(_("Choose the document type"), "VALIDATION_ERROR")
