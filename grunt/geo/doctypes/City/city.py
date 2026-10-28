"""Controller for the ``City`` DocType."""

from grunt.document.base import Document


class City(Document):
    """DocType controller for City."""

    title: str | None
    title_uk: str | None
    country: str | None
    region: str | None
    is_capital: bool | None
    population: int | None
    latitude: float | None
    longitude: float | None
    is_active: bool | None
