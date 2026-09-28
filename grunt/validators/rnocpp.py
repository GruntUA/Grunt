from grunt.i18n import N_
from grunt.validators.base import RegexValidator


class RnocppValidator(RegexValidator):
    name = "rnocpp"
    label = N_("RNOKPP (individual tax number)")
    message = N_("Field “{label}”: invalid RNOKPP (10 digits)")
    pattern = r"^\d{10}$"

    def check(self, value: str) -> bool:
        return super().check(value.strip())
