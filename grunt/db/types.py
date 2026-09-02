"""SQLAlchemy column types shared across Grunt.

``UtcDateTime`` — every datetime in Grunt is UTC. Postgres round-trips
tz-aware values already; SQLite drops the offset and hands back a *naive*
datetime, so the wall-clock reads as UTC but nothing says so. Downstream
``.isoformat()`` / JSON encoders then emit a bare ``2026-08-31T08:18:52``,
which the frontend (and any ISO parser) reads as *local* time — shifting
every timestamp by the viewer's UTC offset.

This decorator closes the gap on both ends:

* bind — a naive value is assumed UTC; an aware value is converted to UTC.
* result — a naive value coming back gets ``tzinfo=UTC`` reattached.

So Python always sees aware-UTC and every serialiser downstream emits an
explicit ``+00:00`` the client can localise.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """A timezone-aware ``DateTime`` that always speaks UTC in and out."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
