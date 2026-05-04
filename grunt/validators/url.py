from grunt.validators.base import RegexValidator


class UrlValidator(RegexValidator):
    name = "url"
    label = "URL / посилання"
    message = "Поле '{label}': невірний формат URL"
    pattern = r"^https?://[^\s/$.?#].[^\s]*$"
