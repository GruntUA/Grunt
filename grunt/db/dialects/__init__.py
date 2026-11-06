"""Database dialects - the only place that tells SQLite from PostgreSQL.

Everything that differs between backends lives on a :class:`Dialect`:
engine setup, SQL expressions (sorting, date buckets, LIKE), schema DDL quirks
and maintenance (size, compaction). Code elsewhere asks :func:`dialect_for`
and calls a method - comparing ``dialect.name`` outside this package is
forbidden (``tests/test_dialect_boundary.py``).

See ``DB_LAYERS_PLAN.md``.
"""

from typing import Any

from sqlalchemy.engine import URL
from sqlalchemy.engine.interfaces import Dialect as SADialect

from grunt.db.dialects.base import Dialect
from grunt.db.dialects.mysql import MysqlDialect
from grunt.db.dialects.postgresql import PostgresDialect
from grunt.db.dialects.sqlite import SqliteDialect

_BY_NAME: dict[str, Dialect] = {
    d.name: d for d in (SqliteDialect(), PostgresDialect(), MysqlDialect())
}
_BY_NAME["mariadb"] = _BY_NAME["mysql"]


class UnknownDatabaseError(RuntimeError):
    """The backend of an object can't be determined or Grunt does not support it."""


def dialect_name(obj: Any) -> str | None:
    """Backend name of a URL, engine, connection, session or SQLAlchemy dialect.

    ``None`` when *obj* carries none - e.g. a session without a bind.
    """
    if obj is None:
        return None
    if isinstance(obj, str):
        # a bare name ("sqlite") or a URL ("postgresql+asyncpg://...")
        return obj.split(":", 1)[0].split("+", 1)[0] or None
    if isinstance(obj, URL):
        return obj.get_backend_name()
    if isinstance(obj, SADialect):
        return obj.name
    sa_dialect = getattr(obj, "dialect", None)
    if sa_dialect is None:
        sa_dialect = getattr(getattr(obj, "bind", None), "dialect", None)
    return getattr(sa_dialect, "name", None)


def dialect_for(obj: Any) -> Dialect:
    """The :class:`Dialect` of *obj* (see :func:`dialect_name`).

    Raises :class:`UnknownDatabaseError` when the backend can't be told or is
    not supported - Grunt never guesses which SQL to generate.
    """
    if isinstance(obj, Dialect):
        return obj
    name = dialect_name(obj)
    if name is None:
        raise UnknownDatabaseError(f"Cannot tell the database backend of {obj!r}")
    try:
        return _BY_NAME[name]
    except KeyError:
        supported = ", ".join(sorted(_BY_NAME))
        raise UnknownDatabaseError(
            f"Unsupported database backend “{name}” (supported: {supported})"
        ) from None


def current_dialect() -> Dialect:
    """Dialect of the active session (raises outside of one)."""
    import grunt

    return dialect_for(grunt.get_session())


__all__ = [
    "Dialect",
    "MysqlDialect",
    "PostgresDialect",
    "SqliteDialect",
    "UnknownDatabaseError",
    "current_dialect",
    "dialect_for",
    "dialect_name",
]
