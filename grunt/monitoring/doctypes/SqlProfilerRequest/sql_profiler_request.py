"""Virtual DocType controller - SQL Profiler Requests.

Exposes the in-memory profiler ring buffer as a standard Grunt DocType.
Read-only: list + load. Insert/update/delete are not supported.
"""

from typing import Any

from grunt.db.profiler import get_recent_requests
from grunt.document.base import Document
from grunt.i18n import N_
from grunt.query.query import Query
from grunt.store import VirtualStore


class SqlProfilerRequestStore(VirtualStore):
    not_supported_message = N_("Profiled requests are read-only")

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        return [self._to_doc(r) for r in get_recent_requests(limit=200)]

    @staticmethod
    def _to_doc(row: dict[str, Any]) -> dict[str, Any]:
        request_id = row["request_id"]
        queries = [
            {
                "name": f"{request_id}-q{idx}",
                "idx": idx,
                **q,
            }
            for idx, q in enumerate(row.get("queries", []))
        ]
        spans = [
            {
                "name": f"{request_id}-s{idx}",
                "method": s["name"],
                "duration_ms": s["duration_ms"],
                "idx": idx,
            }
            for idx, s in enumerate(row.get("spans", []))
        ]
        return {
            "name": request_id,
            "method": row["method"],
            "path": row["path"],
            "status_code": row["status_code"],
            "duration_ms": row["duration_ms"],
            "query_count": row["query_count"],
            "total_query_ms": row["total_query_ms"],
            "slow_query_count": row["slow_query_count"],
            "slow": row.get("slow", False),
            "spans": spans,
            "queries": queries,
        }


class SqlProfilerRequest(Document):
    store_class = SqlProfilerRequestStore
