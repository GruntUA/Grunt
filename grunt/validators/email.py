from grunt.validators.base import RegexValidator


class EmailValidator(RegexValidator):
    name = "email"
    label = "Email"
    message = "Поле '{label}': невірний формат email"
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
