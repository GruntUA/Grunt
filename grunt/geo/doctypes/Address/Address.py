from __future__ import annotations

from grunt.document.base import Document


class Address(Document):
    address_type: str | None
    country: str | None
    region: str | None
    city: str | None
    city_text: str | None
    zip_code: str | None
    street: str | None
    building: str | None
    apartment: str | None
    full_address: str | None
    notes: str | None

    async def validate(self) -> None:
        if not self.city and not self.city_text:
            self.grunt.throw("Необхідно вказати місто: оберіть зі списку або введіть текстом")

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
