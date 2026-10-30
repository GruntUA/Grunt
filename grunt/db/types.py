"""SQLAlchemy column types shared across Grunt.

``UtcDateTime`` - every datetime in Grunt is UTC. Postgres round-trips
tz-aware values already; SQLite drops the offset and hands back a *naive*
datetime, so the wall-clock reads as UTC but nothing says so. Downstream
``.isoformat()`` / JSON encoders then emit a bare ``2026-08-31T08:18:52``,
which the frontend (and any ISO parser) reads as *local* time - shifting
every timestamp by the viewer's UTC offset.

This decorator closes the gap on both ends:

* bind - a naive value is assumed UTC; an aware value is converted to UTC.
* result - a naive value coming back gets ``tzinfo=UTC`` reattached.

So Python always sees aware-UTC and every serialiser downstream emits an
explicit ``+00:00`` the client can localise.

``IsoDate`` / ``UtcDateTime`` also take an ISO string on bind. A loaded
document holds its dates as ISO strings, so a hook that copies one back into
``self.data`` would otherwise hit the plain bind processors, which reject a
``str`` (SQLite: ``TypeError``).
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Date, DateTime
from sqlalchemy.types import TypeDecorator


class IsoDate(TypeDecorator):
    """A ``Date`` that also binds an ISO string (a datetime one is cut to its date)."""

    impl = Date
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, str):
            return date.fromisoformat(value[:10]) if value else None
        return value


class UtcDateTime(TypeDecorator):
    """A timezone-aware ``DateTime`` that always speaks UTC in and out."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, str):
            if not value:
                return None
            value = datetime.fromisoformat(value.replace(" ", "T"))
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
