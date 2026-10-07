"""Virtual DocType controller - SQL Profiler Requests.

Exposes the in-memory profiler ring buffer as a standard Grunt DocType.
Read-only: list + load. Insert/update/delete are not supported.
"""

from __future__ import annotations

from typing import Any

from grunt import _
from grunt.db.profiler import get_recent_requests
from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import apply_filters, apply_search, apply_sort, build_response
from grunt.errors import not_found


class SqlProfilerRequest(BaseDocument):
    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "duration_ms",
        sort_order: str = "desc",
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        **kwargs: Any,
    ) -> DocumentList:
        rows = get_recent_requests(limit=200)

        if search:
            rows = apply_search(rows, search, ["path", "method"])
        if filters:
            rows = apply_filters(rows, filters)
        rows = apply_sort(rows, sort_by, sort_order)

        response = build_response(rows, page, per_page)
        return DocumentList([cls._to_doc(r) for r in response], response.meta)

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        for row in get_recent_requests(limit=200):
            if row["request_id"] == self.name:
                self.data = self._to_doc(row)
                return
        raise not_found(_("SqlProfilerRequest '%(doc_id)s' not found") % {"doc_id": self.name})

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
