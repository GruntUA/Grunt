"""Controller for the ``Page`` DocType."""

from grunt.document.base import Document


class Page(Document):
    """DocType controller for Page."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    label: str  # Name
    description: str | None = None  # Description
    is_published: bool | None = None  # Published
    roles: str | None = None  # Roles (comma-separated)
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App
    widgets: list[dict] = []  # Table: PageWidget

    # end: auto-generated types
