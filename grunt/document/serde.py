"""Small pure helpers for document (de)serialisation and audit fields.

A document is a JSON object that names its own DocType - ``{"doctype":
"Invoice", "name": ..., "items": [{"doctype": "InvoiceItem", ...}]}`` - and
that object is enough to recreate it (``grunt.get_doc(data).insert()``).
"""

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any


def with_doctype(doctype: str, data: dict[str, Any]) -> dict[str, Any]:
    """*data* with ``"doctype"`` as its first key."""
    return {"doctype": doctype, **{k: v for k, v in data.items() if k != "doctype"}}


def json_default(value: Any) -> Any:
    """``json.dumps`` fallback for the values a document holds - and for a
    document (a controller: its JSON, ``doc.as_dict()``). Anything else raises
    ``TypeError``, as ``json.dumps`` does: a ``str()`` of it would ship
    ``"<Invoice id='INV-1'>"`` instead of the data."""
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return as_dict()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def same_instant(a: Any, b: Any) -> bool:
    """Whether two timestamps - datetimes or ISO strings (``Z`` / offset /
    naive-UTC, ``T`` or space) - are the same moment."""

    def parse(v: Any) -> datetime | None:
        if isinstance(v, datetime):
            dt = v
        elif isinstance(v, str) and v:
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    pa, pb = parse(a), parse(b)
    return pa is not None and pb is not None and pa == pb


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
