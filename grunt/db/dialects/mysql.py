"""MySQL / MariaDB."""

from typing import Any

from sqlalchemy import String, cast, func, literal, text

from grunt.db.dialects.base import Dialect

_SIZE_SQL = (
    "SELECT data_length, index_length, data_free FROM information_schema.tables "
    "WHERE table_schema = DATABASE() AND table_name = :t"
)


class MysqlDialect(Dialect):
    name = "mysql"
    compaction_scope = "table"

    def engine_kwargs(self) -> dict[str, Any]:
        return {"pool_size": 20, "max_overflow": 10, "connect_args": {"charset": "utf8mb4"}}

    def date_bucket(self, column: Any, bucket: str) -> Any:
        if bucket == "quarter":
            return func.concat(func.year(column), literal("-Q"), cast(func.quarter(column), String))
        fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}
        return func.date_format(column, fmt[bucket])

    def group_concat_sql(self, expr: str) -> str:
        return f"GROUP_CONCAT({expr})"

    def compaction_command(self, quoted_table: str) -> str:
        return f"OPTIMIZE TABLE {quoted_table}"

    def compaction_footprint(self, conn: Any, table_name: str) -> int | None:
        row = conn.execute(text(_SIZE_SQL), {"t": table_name}).first()
        return int((row[0] or 0) + (row[1] or 0)) if row else 0

    def table_storage(self, conn: Any, table_name: str) -> dict[str, Any]:
        row = conn.execute(text(_SIZE_SQL), {"t": table_name}).first()
        if not row:
            return {}
        return {
            "table_bytes": int(row[0] or 0),
            "index_bytes": int(row[1] or 0),
            "total_bytes": int((row[0] or 0) + (row[1] or 0)),
            "reclaimable_bytes": int(row[2] or 0),
            "reclaim_scope": "table",
            "size_supported": True,
        }
