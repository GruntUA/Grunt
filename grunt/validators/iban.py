from grunt.validators.base import Validator
import re

_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{1,30}$")


class IbanValidator(Validator):
    name = "iban"
    label = "IBAN (міжнародний)"
    message = "Поле '{label}': невірний формат IBAN"

    def check(self, value: str) -> bool:
        return bool(_RE.match(value.replace(" ", "").upper()))
