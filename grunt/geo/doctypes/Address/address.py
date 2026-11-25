from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _


class Address(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    address_type: str | None = None  # Address type
    country: str  # Country
    region: str | None = None  # Region / Oblast
    city: str | None = None  # City (directory)
    city_text: str | None = None  # City (text)
    zip_code: str | None = None  # Postal code
    street: str | None = None  # Street
    building: str | None = None  # Building
    apartment: str | None = None  # Apartment / Office
    full_address: str | None = None  # Full address
    notes: str | None = None  # Notes

    # end: auto-generated types

    async def validate(self) -> None:
        if not self.city and not self.city_text:
            throw(_("A city is required: pick one from the list or type it in"))

    async def on_load(self) -> None:
        self.full_address = self._build_full_address()

    async def before_save(self) -> None:
        self.full_address = self._build_full_address()

    def _build_full_address(self) -> str:
        city_display = self.city_text or self.city or ""
        parts = [
            self.zip_code or "",
            self.country or "",
            self.region or "",
            city_display,
            self.street or "",
            " ".join(filter(None, [self.building, self.apartment])),
        ]
        return ", ".join(p for p in parts if p)
