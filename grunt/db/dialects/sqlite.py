"""SQLite - the default backend of a site (``sites/<site>/grunt.db``)."""

import re
import shutil
import sqlite3
import tempfile
import unicodedata
from compression import zstd
from contextlib import suppress
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, String, Table, bindparam, cast, event, func, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.dml import Insert

from grunt import log
from grunt.db.dialects.base import (
    LIKE_ESCAPE,
    ConstraintViolation,
    Dialect,
    DumpEstimate,
    escape_like,
)
from grunt.db.dialects.fulltext import FullText, FullTextSpec, SqliteFts5
from grunt.db.write_intent import begin_statement
from grunt.i18n import _
lazy from grunt.backups import BackupError, zstd_options

# "NOT NULL constraint failed: t.c", "UNIQUE constraint failed: t.a, t.b"
_SQLITE_COLUMNS_FAILED = re.compile(
    r"(NOT NULL|UNIQUE) constraint failed:\s*([\w.]+(?:,\s*[\w.]+)*)"
)
_SQLITE_CHECK_FAILED = re.compile(r"CHECK constraint failed:\s*(\w+)")

_UK_ALPHABET = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"
_UK_ORDER = {ch: i for i, ch in enumerate(_UK_ALPHABET)}


def uk_sort_key(s: str) -> str:
    """Return a sort key string that respects Ukrainian alphabetical order.

    Maps each Ukrainian letter to a code point in the Private Use Area
    (U+E000+) so that comparison of resulting strings gives correct
    Ukrainian alphabetical order, regardless of Unicode code points.
    """
    if not s:
        return ""
    out = []
    for ch in unicodedata.normalize("NFC", s).casefold():
        pos = _UK_ORDER.get(ch)
        if pos is not None:
            out.append(chr(0xE000 + pos))  # Private Use Area, keeps uk order
        else:
            out.append(ch)
    return "".join(out)


def _unicode_lower(s: Any) -> Any:
    return s.lower() if isinstance(s, str) else s


def register_sqlite_functions(dbapi_conn: Any) -> None:
    """Register Grunt's SQL functions on a raw SQLite connection.

    * ``uk_sort_key()`` - Ukrainian alphabetical sort key.
    * ``lower()`` - overrides SQLite's ASCII-only built-in with a
      Unicode-aware version so that ILIKE (which compiles to
      ``lower(x) LIKE lower(y)``) works for Cyrillic.

    Every SQLite engine - site engines and test engines alike - must have
    these, otherwise search behaves differently under test.
    """
    dbapi_conn.create_function("uk_sort_key", 1, uk_sort_key, deterministic=True)
    dbapi_conn.create_function("lower", 1, _unicode_lower, deterministic=True)


class SqliteDialect(Dialect):
    name = "sqlite"
    file_based = True
    can_alter_column_type = False
    vacuum_sql = "VACUUM"
    compaction_scope = "database"  # VACUUM rewrites the whole file, not one table

    # ── Engine ──────────────────────────────────────────────────────────────

    def resolve_url(self, url: str, base_dir: Path) -> str:
        # "sqlite+aiosqlite:///./grunt.db" -> "sqlite+aiosqlite:////abs/site/grunt.db"
        if "///." not in url:
            return url
        driver, _, rel_path = url.partition("///")
        return f"{driver}///{(base_dir / rel_path).resolve()}"

    def engine_kwargs(self) -> dict[str, Any]:
        # A real (small) pool instead of NullPool: NullPool opens a brand
        # new aiosqlite connection - a new background thread plus the
        # connect-time PRAGMAs below - on every single checkout, which
        # showed up as tens of ms hiding inside the profiler's "BEGIN"
        # span on every request. WAL mode lets several connections read
        # concurrently, and connect_args timeout is SQLite's busy_timeout
        # for the rare writer/writer contention, so pooling is safe here.
        return {"pool_size": 5, "max_overflow": 5, "connect_args": {"timeout": 30}}

    def setup_engine(self, engine: AsyncEngine) -> None:
        @event.listens_for(engine.sync_engine, "connect")
        def _on_connect(dbapi_conn: Any, _connection_record: Any) -> None:
            # Hand transaction control fully to SQLAlchemy: pysqlite/aiosqlite's
            # own implicit BEGIN/COMMIT heuristics otherwise race with
            # SAVEPOINT (session.begin_nested()) boundaries, causing stray
            # implicit commits (and, under WAL, real fsync stalls) exactly
            # at nested-transaction points.
            dbapi_conn.isolation_level = None
            with suppress(Exception):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                # Automatically return freed pages to the OS over time
                # (INCREMENTAL = pages freed lazily, no full-file rewrite)
                cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")
                cursor.close()
                register_sqlite_functions(dbapi_conn)

        @event.listens_for(engine.sync_engine, "begin")
        def _on_begin(conn: Any) -> None:
            # IMMEDIATE for work that will write - see grunt/db/write_intent.py.
            conn.exec_driver_sql(begin_statement())

    def attach_functions(self, engine: AsyncEngine) -> None:
        @event.listens_for(engine.sync_engine, "connect")
        def _on_connect(dbapi_conn: Any, _connection_record: Any) -> None:
            register_sqlite_functions(dbapi_conn)

    # ── Expressions ─────────────────────────────────────────────────────────

    def text_sort(self, col: Any) -> Any:
        # uk_sort_key() is registered on every connection (see setup_engine)
        return func.uk_sort_key(col)

    def like_contains(self, col: Any, term: str) -> Any:
        # ILIKE compiles to ``lower(col) LIKE lower(?)`` and Grunt overrides
        # ``lower()`` with a Python function (SQLite's own is ASCII-only), which
        # costs a Python call per row. For an ASCII-only term the native LIKE is
        # already case-insensitive *and* correct - a non-ASCII character in the
        # column can never equal an ASCII pattern character - so the common
        # searches for codes, numbers and e-mails stay in C.
        if term.isascii():
            return col.like(f"%{escape_like(term)}%", escape=LIKE_ESCAPE)
        return super().like_contains(col, term)

    def upsert(self, table: Table, row: dict[str, Any], key: list[str]) -> Insert:
        stmt = sqlite_insert(table).values(**row)
        return stmt.on_conflict_do_update(
            index_elements=key, set_={k: v for k, v in row.items() if k not in key}
        )

    def fulltext(self, spec: FullTextSpec) -> FullText:
        return SqliteFts5(spec)

    def date_bucket(self, column: Any, bucket: str) -> Any:
        if bucket == "quarter":
            quarter = (cast(func.strftime("%m", column), Integer) + 2) // 3
            return func.strftime("%Y", column).op("||")("-Q").op("||")(cast(quarter, String))
        fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}
        return func.strftime(fmt[bucket], column)

    def group_concat_sql(self, expr: str) -> str:
        return f"GROUP_CONCAT({expr})"

    # ── Schema ──────────────────────────────────────────────────────────────

    def drop_unique_index(
        self, connection: Any, table_name: str, name: str, *, is_index: bool
    ) -> bool:
        if not is_index:
            # Declared inline in CREATE TABLE - DROP INDEX can't reach it.
            return False
        connection.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
        return True

    def drop_inline_unique(self, connection: Any, table_name: str, names: list[str]) -> int:
        """Drop named constraints declared inside SQLite's CREATE TABLE.

        SQLite has no ``DROP CONSTRAINT``: the table is rebuilt from its own stored
        ``CREATE TABLE`` minus those clauses (so every column, type and the other
        constraints stay as they are), rows copied over, indexes and triggers
        recreated. Done in a savepoint - on any failure nothing changes and the
        constraint is reported instead.
        """
        sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :t"),
            {"t": table_name},
        ).scalar_one()
        for name in names:
            clause = re.compile(rf',\s*CONSTRAINT\s+"?{re.escape(name)}"?\s+UNIQUE\s*\([^)]*\)')
            sql, found = clause.subn("", sql)
            if not found:
                for n in names:
                    log.warning(
                        "compiler.unique_inline_not_dropped", table=table_name, constraint=n
                    )
                return 0

        tmp = f"{table_name}__rebuild"
        create_tmp = re.sub(
            rf'^CREATE TABLE\s+"?{re.escape(table_name)}"?', f'CREATE TABLE "{tmp}"', sql, count=1
        )
        extras = (
            connection.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE tbl_name = :t "
                    "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
                ),
                {"t": table_name},
            )
            .scalars()
            .all()
        )
        try:
            with connection.begin_nested():
                connection.execute(text(create_tmp))
                connection.execute(text(f'INSERT INTO "{tmp}" SELECT * FROM "{table_name}"'))
                connection.execute(text(f'DROP TABLE "{table_name}"'))
                connection.execute(text(f'ALTER TABLE "{tmp}" RENAME TO "{table_name}"'))
                for statement in extras:
                    connection.execute(text(statement))
        except Exception as exc:
            for name in names:
                log.warning(
                    "compiler.unique_inline_not_dropped",
                    table=table_name,
                    constraint=name,
                    error=str(exc),
                )
            return 0
        for name in names:
            log.info("compiler.unique_dropped", table=table_name, constraint=name, rebuilt=True)
        return len(names)

    # ── Errors ──────────────────────────────────────────────────────────────

    def integrity_violation(self, exc: Exception) -> ConstraintViolation | None:
        message = str(getattr(exc, "orig", None) or exc)
        if m := _SQLITE_COLUMNS_FAILED.search(message):
            qualified = [c.strip() for c in m.group(2).split(",") if c.strip()]
            table = qualified[0].rpartition(".")[0] or None
            columns = tuple(c.rpartition(".")[2] for c in qualified)
            kind = "not_null" if m.group(1) == "NOT NULL" else "unique"
            return ConstraintViolation(kind, table, columns)
        if "FOREIGN KEY constraint failed" in message:
            return ConstraintViolation("foreign_key")
        if m := _SQLITE_CHECK_FAILED.search(message):
            return ConstraintViolation("check", constraint=m.group(1))
        return None

    # ── Maintenance ─────────────────────────────────────────────────────────

    async def server_version(self, session: Any) -> str:
        return str((await session.execute(text("select sqlite_version()"))).scalar())

    async def database_size(self, session: Any) -> int | None:
        path = session.bind.url.database
        return Path(path).stat().st_size if path and Path(path).exists() else None

    def compaction_command(self, quoted_table: str) -> str:
        return "VACUUM"

    def compaction_footprint(self, conn: Any, table_name: str) -> int | None:
        page_count = int(conn.execute(text("PRAGMA page_count")).scalar() or 0)
        page_size = int(conn.execute(text("PRAGMA page_size")).scalar() or 0)
        return page_count * page_size

    def table_storage(self, conn: Any, table_name: str) -> dict[str, Any]:
        # Needs the ``dbstat`` virtual table (usually compiled in)
        try:
            page_size = int(conn.execute(text("PRAGMA page_size")).scalar() or 0)
            idx_names = [
                r[0]
                for r in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = :t"),
                    {"t": table_name},
                )
            ]
            rows = conn.execute(
                text(
                    "SELECT name, SUM(pgsize) FROM dbstat WHERE name IN :names GROUP BY name"
                ).bindparams(bindparam("names", expanding=True)),
                {"names": [table_name, *idx_names]},
            ).all()
            by_name = {r[0]: int(r[1] or 0) for r in rows}
            tbytes = by_name.get(table_name, 0)
            ibytes = sum(by_name.get(n, 0) for n in idx_names)
            freelist = int(conn.execute(text("PRAGMA freelist_count")).scalar() or 0)
        except Exception:
            log.debug("table_info.dbstat_unavailable", table=table_name)
            return {}
        return {
            "table_bytes": tbytes,
            "index_bytes": ibytes,
            "total_bytes": tbytes + ibytes,
            "size_supported": True,
            # VACUUM works on the whole database file, not one table
            "reclaimable_bytes": freelist * page_size,
            "reclaim_scope": "database",
        }

    # ── Backups ─────────────────────────────────────────────────────────────

    dump_suffix = ".sqlite.zst"

    @staticmethod
    def _db_path(url: Any) -> Path:
        if not url.database:  # in-memory SQLite - no file to back up or restore
            raise BackupError(_("The SQLite database has no file to back up"))
        return Path(url.database)

    def dump_estimate(self, url: Any) -> DumpEstimate:
        size = self._db_path(url).stat().st_size
        # read twice (snapshot, then compressing it); the snapshot lives
        # uncompressed next to the set while it is being compressed
        return DumpEstimate(read=2 * size, output=size, scratch=size)

    def dump(self, url: Any, dest: Path, level: int, progress: Any) -> None:
        """An online snapshot through SQLite's backup API (consistent under WAL,
        unlike copying the file), checked with ``PRAGMA quick_check``, zstd-compressed."""
        db_path = self._db_path(url)
        with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".", suffix=".part") as tmp:
            snapshot = Path(tmp) / "snapshot.sqlite"
            src = sqlite3.connect(db_path)
            dst = sqlite3.connect(snapshot)
            base = progress.done
            page_size = src.execute("PRAGMA page_size").fetchone()[0]

            def copied(_status: int, remaining: int, total: int) -> None:
                progress.set(done=base + (total - remaining) * page_size)

            try:
                progress.set(stage=_("Copying the database"))
                # consistent snapshot, readers/writers keep working between the steps
                src.backup(dst, pages=4096, progress=copied)
                progress.set(stage=_("Checking the database copy"))
                result = dst.execute("PRAGMA quick_check").fetchone()[0]
            finally:
                dst.close()
                src.close()
            if result != "ok":
                raise BackupError(
                    _("The database snapshot is corrupted: %(result)s") % {"result": result}
                )
            progress.set(done=base + snapshot.stat().st_size, stage=_("Compressing the database"))
            with (
                snapshot.open("rb") as fin,
                zstd.open(dest, "wb", options=zstd_options(level)) as fout,
            ):
                while chunk := fin.read(1024 * 1024):
                    fout.write(chunk)
                    progress.advance(len(chunk))

    def restore_dump(self, url: Any, src: Path, aside: Path) -> None:
        db_path = self._db_path(url)
        restored = aside / "restored.sqlite"
        with zstd.open(src, "rb") as fin, restored.open("wb") as fout:
            shutil.copyfileobj(fin, fout, length=1024 * 1024)
        check = sqlite3.connect(restored)
        try:
            result = check.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            check.close()
        if result != "ok":
            raise BackupError(
                _("The database backup is corrupted: %(result)s") % {"result": result}
            )
        for suffix in ("", "-wal", "-shm"):
            current = Path(f"{db_path}{suffix}")
            if current.exists():
                shutil.move(current, aside / current.name)
        shutil.move(restored, db_path)
