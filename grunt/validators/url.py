from grunt.i18n import N_
from grunt.validators.base import RegexValidator


class UrlValidator(RegexValidator):
    name = "url"
    label = N_("URL / link")
    message = N_("Field “{label}”: invalid URL format")
    pattern = r"^https?://[^\s/$.?#].[^\s]*$"
