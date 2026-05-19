"""Unit tests for class-based field validators."""

from pathlib import Path

import pytest

from grunt.document.validators import list_validators, validate_field_value
from grunt.startup.validators import _find_validator_dirs, load_validators
from grunt.validators.base import RegexValidator, Validator


@pytest.fixture(autouse=True)
def _load():
    load_validators()


# ── Built-ins ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,ok",
    [
        ("user@example.com", True),
        ("user+tag@sub.domain.org", True),
        ("not-an-email", False),
        ("@nodomain.com", False),
    ],
)
def test_email(value, ok):
    assert (validate_field_value("email", value, "Email") is None) == ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("+380501234567", True),
        ("(050) 123-45-67", True),
        ("abc", False),
        ("12", False),
    ],
)
def test_phone(value, ok):
    assert (validate_field_value("phone", value, "Phone") is None) == ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("https://example.com", True),
        ("ftp://example.com", False),
        ("example.com", False),
    ],
)
def test_url(value, ok):
    assert (validate_field_value("url", value, "URL") is None) == ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("UA903052992990004149123456789", True),
        ("UA90 3052 9929 9000 4149 1234 5678 9", True),
        ("UA12345", False),
        ("DE89370400440532013000", False),
    ],
)
def test_iban_ua(value, ok):
    assert (validate_field_value("iban_ua", value, "IBAN") is None) == ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("12345678", True),
        ("1234567890", True),
        ("1234567", False),
    ],
)
def test_edrpou(value, ok):
    assert (validate_field_value("edrpou", value, "ЄДРПОУ") is None) == ok


# ── Edge cases ────────────────────────────────────────────────────────────


def test_empty_skipped():
    assert validate_field_value("email", "", "Email") is None
    assert validate_field_value("email", None, "Email") is None


def test_unknown_returns_none():
    assert validate_field_value("nonexistent", "anything", "Field") is None


# ── list_validators includes field_types ──────────────────────────────────


def test_list_validators_shape():
    validators = list_validators()
    names = {v["name"] for v in validators}
    assert {"email", "phone", "url", "iban_ua", "iban", "edrpou", "rnocpp"} <= names
    for v in validators:
        assert "name" in v
        assert "label" in v
        assert "field_types" in v
        assert isinstance(v["field_types"], list)
        assert len(v["field_types"]) > 0


# ── Class-based API ───────────────────────────────────────────────────────


def test_base_classes_exported():
    assert issubclass(RegexValidator, Validator)


def test_regex_validator_subclass():
    class ZipValidator(RegexValidator):
        name = "zip_ua"
        label = "Індекс"
        message = "Невірний індекс"
        pattern = r"^\d{5}$"

    v = ZipValidator()
    assert v.validate("01001", "Індекс") is None
    assert v.validate("abc", "Індекс") is not None
    assert v.validate("", "Індекс") is None


def test_custom_validate_override():
    class NonEmptyValidator(Validator):
        name = "non_empty_custom"
        label = "Не порожнє"
        message = "Порожнє значення"

        def check(self, value: str) -> bool:
            return bool(value.strip())

        def validate(self, value: str, field_label: str) -> str | None:
            # Override: also validate non-empty values
            if not value or not value.strip():
                return self.message
            return None

    v = NonEmptyValidator()
    assert v.validate("hello", "F") is None
    assert v.validate("   ", "F") is not None


# ── Discovery ─────────────────────────────────────────────────────────────


def test_load_from_custom_dir(tmp_path: Path):
    validator_file = tmp_path / "nhs.py"
    validator_file.write_text(
        "from grunt.validators.base import RegexValidator\n"
        "class NhsValidator(RegexValidator):\n"
        "    name = 'nhs_number'\n"
        "    label = 'NHS Number'\n"
        "    message = 'Невірний NHS номер'\n"
        "    pattern = r'^\\d{10}$'\n"
    )

    from grunt.document.validators import load_from_dir

    count = load_from_dir(tmp_path)
    assert count == 1
    assert validate_field_value("nhs_number", "1234567890", "NHS") is None
    assert validate_field_value("nhs_number", "abc", "NHS") is not None


def test_class_without_name_skipped(tmp_path: Path):
    bad_file = tmp_path / "bad.py"
    bad_file.write_text(
        "from grunt.validators.base import Validator\n"
        "class BadValidator(Validator):\n"
        "    label = 'Bad'\n"
        "    def check(self, v): return True\n"
    )

    from grunt.document.validators import load_from_dir

    count = load_from_dir(tmp_path)
    assert count == 0


def test_base_class_not_registered(tmp_path: Path):
    """Importing base.py itself should not register Validator or RegexValidator."""
    from grunt.document.validators import _REGISTRY, load_from_dir

    before = set(_REGISTRY.keys())
    # load_from_dir skips base.py by name
    import shutil

    shutil.copy(
        Path(__file__).parent.parent.parent / "grunt" / "validators" / "base.py",
        tmp_path / "base.py",
    )
    load_from_dir(tmp_path)
    assert set(_REGISTRY.keys()) == before


def test_find_validator_dirs_includes_grunt():
    dirs = _find_validator_dirs()
    grunt_validators = Path(__file__).parent.parent.parent / "grunt" / "validators"
    assert grunt_validators in dirs
