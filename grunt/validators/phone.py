from grunt.i18n import N_
from grunt.validators.base import RegexValidator


class PhoneValidator(RegexValidator):
    name = "phone"
    label = N_("Phone")
    message = N_("Field “{label}”: invalid phone format")
    pattern = r"^\+?[\d\s\-\(\)]{7,20}$"
