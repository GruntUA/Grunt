"""Small pure helpers for document (de)serialisation and audit fields.

Extracted to remove duplicated row-serialisation loops scattered across the
read/write mixins and the relations helpers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


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
