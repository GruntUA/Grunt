from grunt.i18n import N_
from grunt.validators.base import RegexValidator


class EdrpouValidator(RegexValidator):
    name = "edrpou"
    label = N_("EDRPOU")
    message = N_("Field “{label}”: invalid EDRPOU code (8 or 10 digits)")
    pattern = r"^\d{8}(\d{2})?$"

    def check(self, value: str) -> bool:
        return super().check(value.strip())
