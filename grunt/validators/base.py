"""Base classes for field validators."""

from __future__ import annotations

import re
from typing import ClassVar


class Validator:
    """Abstract base for all field validators.

    Subclass and define ``name``, ``label``, and override ``check()``.
    Optionally override ``validate()`` for multi-step or async-style logic.
    """

    name: ClassVar[str]
    label: ClassVar[str]
    message: ClassVar[str] = "Поле '{label}': невірне значення"
    # Field types for which this validator is relevant (shown in Studio dropdown).
    # Override in subclasses to restrict or expand.
    field_types: ClassVar[list[str]] = ["Data", "Text", "LongText"]

    def check(self, value: str) -> bool:
        """Return True if *value* is valid. Must be overridden."""
        raise NotImplementedError

    def validate(self, value: str, field_label: str) -> str | None:
        """Return an error string on failure, or ``None`` on success.

        Empty / None values are always considered valid here —
        required-field checks are handled separately.
        """
        if value is None or value == "":
            return None
        if not self.check(str(value)):
            return self.message.format(label=field_label, value=value)
        return None


class RegexValidator(Validator):
    """Convenience subclass: define ``pattern`` instead of overriding ``check()``."""

    pattern: ClassVar[str]
    _re: ClassVar[re.Pattern]  # type: ignore[type-arg]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "pattern" in cls.__dict__:
            cls._re = re.compile(cls.pattern)

    def check(self, value: str) -> bool:
        return bool(self._re.match(value))
