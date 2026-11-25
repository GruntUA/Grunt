"""Controller for the ``City`` DocType."""

from grunt.document.base import Document


class City(Document):
    """DocType controller for City."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Name
    title_uk: str | None = None  # Name (Ukrainian)
    country: str  # Country
    region: str | None = None  # Region
    is_capital: bool | None = None  # Capital
    population: int | None = None  # Population
    latitude: float | None = None  # Latitude
    longitude: float | None = None  # Longitude
    is_active: bool | None = None  # Active

    # end: auto-generated types
