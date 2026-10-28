"""Controller for the ``Page`` DocType."""

from typing import Any

from grunt.document.base import Document


class Page(Document):
    """DocType controller for Page."""

    label: str | None
    description: str | None
    is_published: bool | None
    roles: str | None
    widgets: list[dict[str, Any]]  # Table: PageWidget
    is_standard: bool | None
    app: str | None
