from grunt.validators.base import RegexValidator


class PhoneValidator(RegexValidator):
    name = "phone"
    label = "Телефон"
    message = "Поле '{label}': невірний формат телефону"
    pattern = r"^\+?[\d\s\-\(\)]{7,20}$"
