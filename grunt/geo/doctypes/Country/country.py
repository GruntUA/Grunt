"""Controller for the ``Country`` DocType."""

from grunt.document.base import Document


class Country(Document):
    """DocType controller for Country."""

    code: str | None
    code3: str | None
    numeric_code: str | None
    flag_emoji: str | None
    title: str | None
    title_uk: str | None
    continent: str | None
    capital: str | None
    phone_code: str | None
    tld: str | None
    currency: str | None
    official_language: str | None
    is_active: bool | None
