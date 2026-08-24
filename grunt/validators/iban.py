import re

from grunt.validators.base import Validator

_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{1,30}$")


class IbanValidator(Validator):
    """Any-country IBAN — 2-letter country code + 2 check digits + up to 30 chars.

    A valid Ukrainian IBAN also passes this (see IbanUaValidator, whose
    UA-specific 27-digit pattern this one is a superset of) — use this one
    for a field that may hold IBANs from any country, IbanUaValidator when
    the field is Ukraine-only and should reject other countries' IBANs.
    """

    name = "iban"
    label = "IBAN (міжнародний)"
    message = "Поле '{label}': невірний формат IBAN"

    def check(self, value: str) -> bool:
        return bool(_RE.match(value.replace(" ", "").upper()))
