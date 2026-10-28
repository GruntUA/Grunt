"""Controller for the ``EmailLoginToken`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class EmailLoginToken(Document):
    """DocType controller for EmailLoginToken."""

    email: str | None
    code_hash: str | None
    expires_at: datetime | None
    consumed_at: datetime | None
    ip_address: str | None
