"""Small pure helpers for document (de)serialisation and audit fields.

A document is a JSON object that names its own DocType - ``{"doctype":
"Invoice", "name": ..., "items": [{"doctype": "InvoiceItem", ...}]}`` - and
that object is enough to recreate it (``grunt.get_doc(data).insert()``).
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


def with_doctype(doctype: str, data: dict[str, Any]) -> dict[str, Any]:
    """*data* with ``"doctype"`` as its first key."""
    return {"doctype": doctype, **{k: v for k, v in data.items() if k != "doctype"}}


def json_default(value: Any) -> Any:
    """``json.dumps`` fallback for the values a document holds."""
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def to_json(data: Any, *, indent: int | None = None) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent, default=json_default)


def serialize_datetimes(row: dict[str, Any]) -> dict[str, Any]:
    """In-place: convert any datetime value to an ISO-8601 string. Returns row."""
    for k, v in row.items():
        if isinstance(v, datetime):
            row[k] = v.isoformat()
    return row


def audit_fields(user_email: str, now: datetime) -> dict[str, Any]:
    """Return the standard audit columns shared by every persisted row."""
    return {
        "owner": user_email,
        "created_at": now,
        "modified_at": now,
        "modified_by": user_email,
    }
