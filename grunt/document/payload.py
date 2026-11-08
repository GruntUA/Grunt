"""The values an update writes - shared by the pipeline (hooks see them) and
the SQL store (it writes them)."""

from datetime import UTC, datetime
from typing import Any

#: Set on insert, never changed by an update.
PROTECTED_FIELDS = frozenset({"name", "owner", "created_at"})


def update_values(
    dt: Any, data: dict[str, Any], columns: frozenset[str] | None, user_email: str
) -> dict[str, Any]:
    """The submitted changes *data* to write: coerced, without the protected
    fields, stamped ``modified_at``/``modified_by``. *columns* - what a stored
    row can hold (``None`` - any value)."""
    values: dict[str, Any] = {}
    if columns is None:
        for key, value in data.items():
            if key in PROTECTED_FIELDS or key[:2] == "__" or key == "doctype":
                continue
            field = dt.get_field(key)
            values[key] = field.coerce(value) if field and field.is_physical else value
    else:
        for field in dt.get_physical_fields():
            if field.fieldname not in columns:
                continue
            if field.fieldname in data and field.fieldname not in PROTECTED_FIELDS:
                values[field.fieldname] = field.coerce(data[field.fieldname])
    if columns is None or "modified_at" in columns:
        values["modified_at"] = datetime.now(UTC)
    if columns is None or "modified_by" in columns:
        values["modified_by"] = user_email
    return values
