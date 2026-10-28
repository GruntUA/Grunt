"""Controller for the ``Currency`` DocType."""

from grunt.document.base import Document


class Currency(Document):
    """DocType controller for Currency."""

    code: str | None
    title: str | None
    title_uk: str | None
    symbol: str | None
    numeric_code: str | None
    decimal_places: int | None
    is_active: bool | None
