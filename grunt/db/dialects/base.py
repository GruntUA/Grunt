"""Base of the concrete dialects - shared defaults and the methods each must define.

There is no "generic" dialect: Grunt always knows which backend it talks to
(``dialect_for`` raises otherwise). The defaults here are the ANSI /
PostgreSQL-like behaviour several backends share: ``lower()`` for sorting,
``ILIKE`` for contains, ``string_agg`` for concatenation.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Literal, NamedTuple

from sqlalchemy import Table, func, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.dml import Insert

from grunt.db.dialects.fulltext import FullText, FullTextSpec
from grunt.i18n import _
lazy from grunt.backups import BackupError

LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so *term* matches literally."""
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


class ConstraintViolation(NamedTuple):
    """What an ``IntegrityError`` broke, told apart from the driver's wording."""

    kind: Literal["not_null", "unique", "foreign_key", "check"]
    table: str | None = None
    columns: tuple[str, ...] = ()
    #: Constraint or index name, when the backend reports one.
    constraint: str | None = None

    @property
    def column(self) -> str | None:
        """The one column involved, ``None`` for none or several."""
        return self.columns[0] if len(self.columns) == 1 else None


class DumpEstimate(NamedTuple):
    """What a database dump costs, known before it is made (bytes)."""

    #: What the dump reads - the progress bar's measure (0 - unknown, stage only).
    read: int = 0
    #: Upper bound of the dump file on disk.
    output: int = 0
    #: Extra disk needed only while the dump is made (e.g. an uncompressed copy).
    scratch: int = 0


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

    #: The database is a local file (no server, no separate databases on it).
    file_based: ClassVar[bool] = False

    # ── Engine ──────────────────────────────────────────────────────────────

    async def create_database(self, url: Any, name: str, *, replace: bool = False) -> None:
        """Create database *name* on the server *url* points at, unless it exists -
        or, with *replace*, drop it first (connections to it are closed)."""
        raise NotImplementedError(f"“{self.name}” has no server-side databases")

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
    def upsert(self, table: Table, row: dict[str, Any], key: list[str]) -> Insert:
        """INSERT of *row* that updates the other columns when *key* already exists."""

    @abstractmethod
    def fulltext(self, spec: FullTextSpec) -> FullText:
        """The backend's native full-text engine over *spec* (see ``fulltext.py``)."""

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

    async def empty_tables(self, conn: Any, names: list[str]) -> None:
        """Delete every row of the tables *names* - their schema stays (tests)."""
        quote = conn.dialect.identifier_preparer.quote
        for name in names:
            await conn.execute(text(f"DELETE FROM {quote(name)}"))

    def drop_inline_unique(self, connection: Any, table_name: str, names: list[str]) -> int:
        """Drop unique constraints declared inside CREATE TABLE (rebuild-only backends)."""
        return 0

    # ── Errors ──────────────────────────────────────────────────────────────

    @abstractmethod
    def integrity_violation(self, exc: Exception) -> ConstraintViolation | None:
        """What *exc* (an ``IntegrityError`` or the driver's own) violated; ``None`` - unknown."""

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

    # ── Backups (orchestrated by ``grunt.backups``) ─────────────────────────

    #: File suffix of a database dump in a backup set; ``None`` - not supported.
    dump_suffix: ClassVar[str | None] = None

    def dump_estimate(self, url: Any) -> DumpEstimate:
        """Sizes of a dump of the database at *url* (see :class:`DumpEstimate`)."""
        return DumpEstimate()

    def dump(self, url: Any, dest: Path, level: int, progress: Any) -> None:
        """Write a consistent dump of the database at *url* to *dest*.

        *level* - zstd compression level; *progress* - a ``grunt.progress.Progress``
        advanced in :attr:`DumpEstimate.read` bytes. Raises ``BackupError``.
        """
        raise BackupError(_("Backups of %(backend)s are not supported") % {"backend": self.name})

    def restore_dump(self, url: Any, src: Path, aside: Path) -> None:
        """Replace the database at *url* with the dump *src*. The server must be stopped.

        Whatever the backend can move away (a database file) goes to *aside*.
        """
        raise BackupError(_("Restoring %(backend)s is not supported") % {"backend": self.name})
