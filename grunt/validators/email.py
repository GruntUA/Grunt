from grunt.i18n import N_
from grunt.validators.base import RegexValidator


class EmailValidator(RegexValidator):
    name = "email"
    label = "Email"
    message = N_("Field “{label}”: invalid email format")
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
