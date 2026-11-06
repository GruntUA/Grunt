"""PostgreSQL."""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import Table, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql.dml import Insert

from grunt.db.dialects.base import Dialect
from grunt.db.dialects.fulltext import FullText, FullTextSpec, PostgresTsvector
from grunt.i18n import _
lazy from grunt.backups import MAX_COMPRESSION_LEVEL, BackupError


class PostgresDialect(Dialect):
    name = "postgresql"
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

    # ── Backups ─────────────────────────────────────────────────────────────

    dump_suffix = ".pgdump"

    @staticmethod
    def _libpq_url(url: Any) -> str:
        return url.set(drivername="postgresql").render_as_string(hide_password=False)

    def dump(self, url: Any, dest: Path, level: int, progress: Any) -> None:
        """``pg_dump -Fc`` with zstd (pg_dump 16+); its size is unknown up front."""
        if not shutil.which("pg_dump"):
            raise BackupError(_("pg_dump not found; install the PostgreSQL client"))
        level = min(max(level, 1), MAX_COMPRESSION_LEVEL)
        progress.set(stage=_("Dumping the database"))  # pg_dump reports no progress
        subprocess.run(
            ["pg_dump", "-Fc", f"--compress=zstd:{level}", "-f", str(dest), self._libpq_url(url)],
            check=True,
        )

    def restore_dump(self, url: Any, src: Path, aside: Path) -> None:
        if not shutil.which("pg_restore"):
            raise BackupError(_("pg_restore not found; install the PostgreSQL client"))
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "-d",
                self._libpq_url(url),
                str(src),
            ],
            check=True,
        )
