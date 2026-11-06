"""PostgreSQL."""

from typing import Any

from sqlalchemy import func, text

from grunt.db.dialects.base import Dialect


class PostgresDialect(Dialect):
    name = "postgresql"
    compaction_scope = "table"

    def engine_kwargs(self) -> dict[str, Any]:
        return {"pool_size": 20, "max_overflow": 10}

    def text_sort(self, col: Any) -> Any:
        # Portable lower(); for full Ukrainian ordering install the ICU
        # collation and sort on ``col.collate("uk-x-icu")``.
        return func.lower(col)

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
