import re

from grunt.i18n import N_
from grunt.validators.base import Validator

_RE = re.compile(r"^UA\d{27}$")


class IbanUaValidator(Validator):
    """Ukraine-only IBAN - exactly "UA" + 27 digits.

    Stricter than IbanValidator (which accepts any country's IBAN, Ukraine's
    included) - use this one when the field must reject non-Ukrainian IBANs,
    the general one when any country is valid.
    """

    name = "iban_ua"
    label = N_("IBAN (Ukraine)")
    message = N_("Field “{label}”: invalid IBAN format (expected UA + 27 digits)")

    def check(self, value: str) -> bool:
        return bool(_RE.match(value.replace(" ", "").upper()))
