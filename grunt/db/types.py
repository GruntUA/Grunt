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

from sqlalchemy import Boolean, Date, DateTime, false, true
from sqlalchemy.sql import operators
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


_FALSE_STRINGS = frozenset({"", "0", "false", "no", "off"})


class CheckBool(TypeDecorator):
    """A ``Boolean`` (Check field) that also binds ``1`` / ``0`` and their strings.

    Code and query strings say ``{"is_active": 1}`` or ``"true"``; SQLite takes
    that as is, PostgreSQL does not (``operator does not exist: boolean =
    integer`` in a WHERE, asyncpg's "expected bool" in a write). Values are
    turned into a real ``bool`` on the way in - in comparisons too, since a
    value compared with this column is bound with this type.
    """

    impl = Boolean
    cache_ok = True

    class Comparator(TypeDecorator.Comparator):
        def operate(self, op: Any, *other: Any, **kwargs: Any) -> Any:
            # ``IS`` takes a constant, not a parameter: ``col.is_(True)`` must
            # render ``IS true`` (as for a plain Boolean) - ``IS $1`` is a
            # syntax error on PostgreSQL.
            if op in (operators.is_, operators.is_not) and other:
                value = other[0]
                if isinstance(value, bool):
                    other = (true() if value else false(), *other[1:])
            return super().operate(op, *other, **kwargs)

    comparator_factory = Comparator  # pyright: ignore[reportAssignmentType] - SQLAlchemy's documented override

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in _FALSE_STRINGS
        return bool(value)

    def coerce_compared_value(self, op: Any, value: Any) -> Any:
        return self
