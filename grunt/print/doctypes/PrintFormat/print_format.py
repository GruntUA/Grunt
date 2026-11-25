"""Controller for the ``PrintFormat`` DocType."""

from grunt.document.base import Document


class PrintFormat(Document):
    """DocType controller for PrintFormat."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str  # Document type
    template_type: str | None = None  # Template type
    is_default: bool | None = None  # Default
    letter_head: str | None = None  # Letter Head
    no_letter_head: bool | None = None  # Without letter head
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App
    template: str  # Template

    # end: auto-generated types
