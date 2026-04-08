"""Validation and type coercion for Documents."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Any

from grunt.core.metadata.field import NON_PHYSICAL_FIELDS

if TYPE_CHECKING:
    from grunt.core.metadata.doctype import DocType


def _coerce_value(value: Any, fieldtype: str) -> Any:
    """Convert string values to proper Python types for SQLAlchemy."""
    # Check fields always coerce to bool — never store NULL
    if fieldtype == "Check":
        if value is None or value == "":
            return False
        return bool(value)
    if value is None or value == "":
        return None if fieldtype in ("Date", "Datetime", "Time", "Int", "Float") else value
    if fieldtype == "Date" and isinstance(value, str):
        return date.fromisoformat(value)
    if fieldtype == "Datetime" and isinstance(value, str):
        return datetime.fromisoformat(value)
    if fieldtype == "Time" and isinstance(value, str):
        return time.fromisoformat(value)
    if fieldtype == "Int" and isinstance(value, str):
        return int(value)
    if fieldtype == "Float" and isinstance(value, str):
        return float(value)
    return value


def _validate_data(
    doctype: DocType, data: dict[str, Any], partial: bool = False
) -> list[str]:
    """Validate document data against DocType fields."""
    errors: list[str] = []
    for field in doctype.fields:
        if field.fieldtype in NON_PHYSICAL_FIELDS:
            continue

        value = data.get(field.fieldname)

        # Required check (skip for partial updates if field not provided)
        if field.required and not partial:
            if value is None or value == "":
                errors.append(f"{field.fieldname}: Поле '{field.label}' є обов'язковим")

    return errors
