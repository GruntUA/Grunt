"""Controller for the ``Language`` DocType."""

from grunt.document.base import Document


class Language(Document):
    """DocType controller for Language."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    code: str  # ISO 639-1 code
    title: str  # Name (English)
    native_name: str | None = None  # Native name
    script: str | None = None  # Script
    is_active: bool | None = None  # Active

    # end: auto-generated types
