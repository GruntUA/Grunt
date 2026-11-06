"""PostgreSQL."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import Table, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql.dml import Insert

from grunt.db.dialects.base import ConstraintViolation, Dialect
from grunt.db.dialects.fulltext import FullText, FullTextSpec, PostgresTsvector
from grunt.i18n import _
lazy from grunt.backups import MAX_COMPRESSION_LEVEL, BackupError

_PG_KINDS = {"23502": "not_null", "23505": "unique", "23503": "foreign_key", "23514": "check"}
_PG_NOT_NULL_COLUMN = re.compile(r'null value in column "([^"]+)"')
_PG_KEY_COLUMNS = re.compile(r"Key \(([^)]+)\)=")
_PG_CONSTRAINT = re.compile(r'constraint "([^"]+)"')
_PG_RELATION = re.compile(r'relation "([^"]+)"')


class PostgresDialect(Dialect):
    name = "postgresql"

    async def create_database(self, url: Any, name: str) -> None:
        # CREATE DATABASE can't run in a transaction and has no IF NOT EXISTS
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                exists = await conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
                )
                if not exists:
                    quoted = conn.dialect.identifier_preparer.quote(name)
                    await conn.execute(text(f"CREATE DATABASE {quoted}"))
        finally:
            await engine.dispose()

    compaction_scope = "table"

    def engine_kwargs(self) -> dict[str, Any]:
        return {"pool_size": 20, "max_overflow": 10}

    def text_sort(self, col: Any) -> Any:
        # Portable lower(); for full Ukrainian ordering install the ICU
        # collation and sort on ``col.collate("uk-x-icu")``.
        return func.lower(col)

    def upsert(self, table: Table, row: dict[str, Any], key: list[str]) -> Insert:
        stmt = pg_insert(table).values(**row)
        return stmt.on_conflict_do_update(
            index_elements=key, set_={k: v for k, v in row.items() if k not in key}
        )

    def fulltext(self, spec: FullTextSpec) -> FullText:
        return PostgresTsvector(spec)

    def date_bucket(self, column: Any, bucket: str) -> Any:
        fmt = {"day": "YYYY-MM-DD", "month": "YYYY-MM", "quarter": 'YYYY-"Q"Q', "year": "YYYY"}
        return func.to_char(column, fmt[bucket])

    async def database_size(self, session: Any) -> int | None:
        return (await session.execute(text("select pg_database_size(current_database())"))).scalar()

    def compaction_command(self, quoted_table: str) -> str:
        # ACCESS EXCLUSIVE on the table while it is rewritten
        return f"VACUUM (FULL, ANALYZE) {quoted_table}"

    def compaction_footprint(self, conn: Any, table_name: str) -> int | None:
        return int(
            conn.execute(text("SELECT pg_total_relation_size(:t)"), {"t": table_name}).scalar() or 0
        )

    def table_storage(self, conn: Any, table_name: str) -> dict[str, Any]:
        row = conn.execute(
            text("SELECT pg_table_size(:t), pg_indexes_size(:t), pg_total_relation_size(:t)"),
            {"t": table_name},
        ).one()
        dead = conn.execute(
            text("SELECT n_dead_tup FROM pg_stat_user_tables WHERE relname = :t"),
            {"t": table_name},
        ).scalar()
        return {
            "table_bytes": int(row[0]),
            "index_bytes": int(row[1]),
            "total_bytes": int(row[2]),
            "size_supported": True,
            "dead_tuples": int(dead or 0),
            "reclaim_scope": "table",
        }

    # ── Errors ──────────────────────────────────────────────────────────────

    def integrity_violation(self, exc: Exception) -> ConstraintViolation | None:
        # SQLAlchemy's asyncpg adapter keeps the SQLSTATE on the DBAPI error and
        # the asyncpg exception (column_name, constraint_name, ...) as its cause.
        orig = getattr(exc, "orig", None) or exc
        native = orig.__cause__ or orig
        code = getattr(orig, "sqlstate", None) or getattr(native, "sqlstate", None)
        kind = _PG_KINDS.get(str(code))
        if kind is None:
            return None
        message = f"{orig}\n{getattr(native, 'detail', '') or ''}"

        column = getattr(native, "column_name", None)
        if column is None and kind == "not_null":
            column = m.group(1) if (m := _PG_NOT_NULL_COLUMN.search(message)) else None
        columns: tuple[str, ...] = (column,) if column else ()
        if not columns and (m := _PG_KEY_COLUMNS.search(message)):
            columns = tuple(c.strip().strip('"') for c in m.group(1).split(","))

        constraint = getattr(native, "constraint_name", None)
        if constraint is None and (m := _PG_CONSTRAINT.search(message)):
            constraint = m.group(1)
        table = getattr(native, "table_name", None)
        if table is None and (m := _PG_RELATION.search(message)):
            table = m.group(1)
        return ConstraintViolation(kind, table, columns, constraint)  # type: ignore[arg-type]

    # ── Backups ─────────────────────────────────────────────────────────────

    dump_suffix = ".pgdump"

    @staticmethod
    def _run_client(tool: str, args: list[str], url: Any) -> None:
        """Run a PostgreSQL client tool against *url*; a failure is a ``BackupError``.

        The password goes in ``PGPASSWORD``, never in the arguments - those are
        visible to every local user in the process list and end up in errors.
        """
        if not shutil.which(tool):
            raise BackupError(
                _("%(tool)s not found; install the PostgreSQL client") % {"tool": tool}
            )
        # URL.set(password=None) keeps the password - build the URL without it
        conninfo = URL.create(
            "postgresql",
            username=url.username,
            host=url.host,
            port=url.port,
            database=url.database,
            query=url.query,
        )
        env = dict(os.environ)
        if url.password:
            env["PGPASSWORD"] = str(url.password)
        result = subprocess.run(
            [tool, *args, conninfo.render_as_string(hide_password=False)],
            env=env,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error = (result.stderr or "").strip().splitlines()[-1:] or [str(result.returncode)]
            raise BackupError(_("%(tool)s failed: %(error)s") % {"tool": tool, "error": error[0]})

    def dump(self, url: Any, dest: Path, level: int, progress: Any) -> None:
        """``pg_dump -Fc`` with zstd (pg_dump 16+); its size is unknown up front."""
        level = min(max(level, 1), MAX_COMPRESSION_LEVEL)
        progress.set(stage=_("Dumping the database"))  # pg_dump reports no progress
        self._run_client("pg_dump", ["-Fc", f"--compress=zstd:{level}", "-f", str(dest)], url)

    def restore_dump(self, url: Any, src: Path, aside: Path) -> None:
        # The database URL goes last as a positional dbname, so -d takes it.
        self._run_client(
            "pg_restore", ["--clean", "--if-exists", "--no-owner", str(src), "-d"], url
        )
