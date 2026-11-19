"""Controller for the ``OutgoingWebhook`` DocType."""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _


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

    async def validate(self) -> None:
        # The document type matters to document events; a webhook only notification
        # rules post to ("notification") has none.
        if self.event != "notification" and not self.doctype_name:
            throw(_("Choose the document type"), "VALIDATION_ERROR")
