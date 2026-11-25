"""Controller for the ``Country`` DocType."""

from grunt.document.base import Document


class Country(Document):
    """DocType controller for Country."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    code: str  # ISO 3166-1 alpha-2 code
    code3: str | None = None  # ISO 3166-1 alpha-3 code
    numeric_code: str | None = None  # Numeric code
    flag_emoji: str | None = None  # Flag
    title: str  # Name (English)
    title_uk: str | None = None  # Name (Ukrainian)
    continent: str | None = None  # Continent
    capital: str | None = None  # Capital
    phone_code: str | None = None  # Dialing code
    tld: str | None = None  # Top-level domain
    currency: str | None = None  # Currency
    official_language: str | None = None  # Official language
    is_active: bool | None = None  # Active

    # end: auto-generated types
