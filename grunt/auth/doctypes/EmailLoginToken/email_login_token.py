"""Controller for the ``EmailLoginToken`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class EmailLoginToken(Document):
    """DocType controller for EmailLoginToken."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    email: str | None = None  # Email
    code_hash: str | None = None  # Code hash
    expires_at: datetime | None = None  # Valid until
    consumed_at: datetime | None = None  # Used
    ip_address: str | None = None  # Request IP address

    # end: auto-generated types
