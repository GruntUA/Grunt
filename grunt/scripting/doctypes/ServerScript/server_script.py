"""Controller for the ``ServerScript`` DocType."""

from grunt.document.base import Document


class ServerScript(Document):
    """DocType controller for ServerScript."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    script_type: str  # Type
    ref_doctype: str | None = None  # Document type
    event: str | None = None  # Event
    api_method: str | None = None  # API method
    cron: str | None = None  # Cron expression
    script: str  # Script (Python)
    is_enabled: bool | None = None  # Active
    allow_guest: bool | None = None  # Allow guests
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App

    # end: auto-generated types
