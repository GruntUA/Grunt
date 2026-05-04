from grunt.validators.base import RegexValidator


class EdrpouValidator(RegexValidator):
    name = "edrpou"
    label = "ЄДРПОУ"
    message = "Поле '{label}': невірний код ЄДРПОУ (8 або 10 цифр)"
    pattern = r"^\d{8}(\d{2})?$"

    def check(self, value: str) -> bool:
        return super().check(value.strip())
