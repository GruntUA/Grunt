"""Base of the concrete dialects - shared defaults and the methods each must define.

There is no "generic" dialect: Grunt always knows which backend it talks to
(``dialect_for`` raises otherwise). The defaults here are the ANSI /
PostgreSQL-like behaviour several backends share: ``lower()`` for sorting,
``ILIKE`` for contains, ``string_agg`` for concatenation.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncEngine

LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so *term* matches literally."""
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


class Dialect(ABC):
    """What Grunt needs from a database backend beyond SQLAlchemy Core."""

    #: SQLAlchemy backend name (``sqlite``, ``postgresql``, ``mysql``).
    name: ClassVar[str]

    #: ``ALTER COLUMN ... TYPE`` is available (SQLite has none).
    can_alter_column_type = True

    #: Statement that reclaims free space of the *whole* database and must run
    #: in AUTOCOMMIT, or ``None`` when the backend does it by itself.
    vacuum_sql: str | None = None

    #: What :meth:`compaction_command` rewrites - ``"table"`` or ``"database"``.
    compaction_scope: ClassVar[str]

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"

    # ── Engine ──────────────────────────────────────────────────────────────

    def resolve_url(self, url: str, base_dir: Path) -> str:
        """Make a site-relative URL absolute (only file-based backends care)."""
        return url

    def engine_kwargs(self) -> dict[str, Any]:
        """Extra ``create_async_engine`` arguments for a site engine."""
        return {}

    def setup_engine(self, engine: AsyncEngine) -> None:
        """Connection-level setup of a site engine (listeners, session settings)."""
        self.attach_functions(engine)

    def attach_functions(self, engine: AsyncEngine) -> None:
        """Register Grunt's SQL functions on every connection (backends that need it)."""
        return None  # nothing to register by default

    # ── Expressions ─────────────────────────────────────────────────────────

    def text_sort(self, col: Any) -> Any:
        """Locale-friendly sort expression for a text column."""
        return func.lower(col)

    def like_contains(self, col: Any, term: str) -> Any:
        """Case-insensitive ``col`` contains ``term``."""
        return col.ilike(f"%{escape_like(term)}%", escape=LIKE_ESCAPE)

    @abstractmethod
    def date_bucket(self, column: Any, bucket: str) -> Any:
        """Label *column* with its day / month / quarter / year (``2026-Q4``)."""

    def group_concat_sql(self, expr: str) -> str:
        """Raw-SQL aggregate joining *expr* values with commas."""
        return f"string_agg(CAST({expr} AS TEXT), ',')"

    # ── Schema (sync connection, inside ``run_sync``) ───────────────────────

    def drop_unique_index(
        self, connection: Any, table_name: str, name: str, *, is_index: bool
    ) -> bool:
        """Drop the unique index/constraint *name*; ``False`` - needs a table rebuild.

        Tried as an index first, then as a constraint - each in a savepoint, so a
        failed attempt does not abort the surrounding transaction (PostgreSQL).
        """
        try:
            with connection.begin_nested():
                connection.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
        except Exception:
            with connection.begin_nested():
                connection.execute(
                    text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{name}"')
                )
        return True

    def drop_inline_unique(self, connection: Any, table_name: str, names: list[str]) -> int:
        """Drop unique constraints declared inside CREATE TABLE (rebuild-only backends)."""
        return 0

    # ── Maintenance ─────────────────────────────────────────────────────────

    async def server_version(self, session: Any) -> str:
        return str((await session.execute(text("select version()"))).scalar())

    async def database_size(self, session: Any) -> int | None:
        """Bytes the database takes, ``None`` when unknown."""
        return None

    @abstractmethod
    def compaction_command(self, quoted_table: str) -> str:
        """Statement that compacts a table (runs in AUTOCOMMIT), see :attr:`compaction_scope`."""

    def compaction_footprint(self, conn: Any, table_name: str) -> int | None:
        """Bytes a compaction can shrink, in the scope :meth:`compaction` reports."""
        return None

    def table_storage(self, conn: Any, table_name: str) -> dict[str, Any]:
        """On-disk size of a table: ``table_bytes``, ``index_bytes``, ``total_bytes``,
        ``reclaimable_bytes``, ``reclaim_scope``, ``size_supported`` - best effort."""
        return {}
