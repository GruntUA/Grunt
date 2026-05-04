from grunt.validators.base import RegexValidator


class RnocppValidator(RegexValidator):
    name = "rnocpp"
    label = "РНОКПП (ІПН)"
    message = "Поле '{label}': невірний РНОКПП (10 цифр)"
    pattern = r"^\d{10}$"

    def check(self, value: str) -> bool:
        return super().check(value.strip())
