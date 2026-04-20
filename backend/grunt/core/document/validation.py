"""Validation and type coercion for Documents."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from grunt.core.metadata.field import NON_PHYSICAL_FIELDS

if TYPE_CHECKING:
    from grunt.core.metadata.doctype import DocType


def _coerce_value(value: Any, fieldtype: str) -> Any:
    """Convert string values to proper Python types for SQLAlchemy."""
    from grunt.core.metadata.field import _SA_TYPE_MAP  # noqa: PLC0415

    # Check fields always coerce to bool — never store NULL
    if fieldtype == "Check":
        if value is None or value == "":
            return False
        return bool(value)

    # Determine the SA type name for this fieldtype (built-in or registered)
    factory = _SA_TYPE_MAP.get(fieldtype)
    try:
        sa_type = factory(None)[0] if factory else fieldtype
    except Exception:
        sa_type = fieldtype  # fallback if factory requires field attributes

    _NULL_TYPES = {"Date", "Datetime", "Time", "Integer", "Float"}
    if value is None or value == "":
        return None if (fieldtype in ("Date", "Datetime", "Time", "Int") or sa_type in _NULL_TYPES) else value

    if fieldtype == "Date" and isinstance(value, str):
        # Accept both "YYYY-MM-DD" and "YYYY-MM-DD HH:MM:SS" / full ISO datetime
        return date.fromisoformat(value[:10])
    if fieldtype == "Datetime" and isinstance(value, str):
        return datetime.fromisoformat(value.replace(" ", "T"))
    if fieldtype == "Time" and isinstance(value, str):
        return time.fromisoformat(value)
    if (fieldtype == "Int" or sa_type == "Integer") and isinstance(value, str):
        try:
            return int(float(value))  # handles "1.0" → 1
        except ValueError:
            return None
    if (fieldtype == "Float" or sa_type == "Float") and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return value


def _validate_data(
    doctype: DocType,
    data: dict[str, Any],
    partial: bool = False,
    ignore_required: bool = False,
) -> list[str]:
    """Validate document data against DocType fields."""
    errors: list[str] = []
    for field in doctype.fields:
        if field.fieldtype in NON_PHYSICAL_FIELDS:
            continue

        value = data.get(field.fieldname)

        # Required check (skip for partial updates, ignore_required flag, or if a default will be applied)
        if (
            field.required
            and not partial
            and not ignore_required
            and (value is None or value == "")
            and field.default is None
        ):
            errors.append(f"{field.fieldname}: Поле '{field.label}' є обов'язковим")

    return errors
