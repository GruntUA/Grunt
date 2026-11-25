"""Controller for the ``Currency`` DocType."""

from grunt.document.base import Document


class Currency(Document):
    """DocType controller for Currency."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    code: str  # ISO 4217 code
    title: str  # Name (English)
    title_uk: str | None = None  # Name (Ukrainian)
    symbol: str | None = None  # Symbol
    numeric_code: str | None = None  # Numeric code
    decimal_places: int | None = None  # Decimal places
    is_active: bool | None = None  # Active

    # end: auto-generated types
