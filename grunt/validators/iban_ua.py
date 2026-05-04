from grunt.validators.base import Validator
import re

_RE = re.compile(r"^UA\d{27}$")


class IbanUaValidator(Validator):
    name = "iban_ua"
    label = "IBAN (Україна)"
    message = "Поле '{label}': невірний формат IBAN (очікується UA + 27 цифр)"

    def check(self, value: str) -> bool:
        return bool(_RE.match(value.replace(" ", "").upper()))
