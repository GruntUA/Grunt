"""Controller for the ``ClientScript`` DocType."""

from grunt.document.base import Document


class ClientScript(Document):
    """DocType controller for ClientScript."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str  # Document type
    script: str  # Script (JavaScript)
    is_enabled: bool | None = None  # Active
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App

    # end: auto-generated types
