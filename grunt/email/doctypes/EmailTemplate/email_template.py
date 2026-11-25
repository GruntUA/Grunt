"""Controller for the ``EmailTemplate`` DocType."""

from grunt.document.base import Document


class EmailTemplate(Document):
    """DocType controller for EmailTemplate."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    label: str  # Name
    is_active: bool | None = None  # Active
    subject: str  # Email subject
    body: str  # Text (plain)
    body_html: str | None = None  # Text (HTML)
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App
    description: str | None = None  # Where used / available fields

    # end: auto-generated types
