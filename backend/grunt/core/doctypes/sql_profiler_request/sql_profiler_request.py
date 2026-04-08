"""Virtual DocType controller — SQL Profiler Requests.

Exposes the in-memory profiler ring buffer as a standard Grunt DocType.
Read-only: list + get. Create/update/delete are not supported.
"""
from __future__ import annotations

from typing import Any

from grunt.core.metadata.virtual import VirtualDocType


class SqlProfilerRequest(VirtualDocType):

    async def get_list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "duration_ms",
        sort_order: str = "desc",
        search: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from grunt.core.db.profiler import get_recent_requests  # noqa: PLC0415

        rows = get_recent_requests(limit=200)

        if search:
            rows = self.apply_search(rows, search, ["path", "method"])
        if filters:
            rows = self.apply_filters(rows, filters)
        rows = self.apply_sort(rows, sort_by, sort_order)

        response = self.build_response(rows, page, per_page)
        response["data"] = [self._to_doc(r) for r in response["data"]]
        return response

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        from grunt.core.db.profiler import get_recent_requests  # noqa: PLC0415
        from fastapi import HTTPException, status  # noqa: PLC0415

        rows = get_recent_requests(limit=200)
        for row in rows:
            if row["request_id"] == doc_id:
                return self._to_doc(row)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SqlProfilerRequest '{doc_id}' not found",
        )

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        from fastapi import HTTPException, status  # noqa: PLC0415
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Read-only")

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        from fastapi import HTTPException, status  # noqa: PLC0415
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Read-only")

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        from fastapi import HTTPException, status  # noqa: PLC0415
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Read-only")

    @staticmethod
    def _to_doc(row: dict[str, Any]) -> dict[str, Any]:
        request_id = row["request_id"]
        queries = [
            {
                "id":         f"{request_id}-q{idx}",
                "name":       f"{request_id}-q{idx}",
                "idx":        idx,
                **q,
            }
            for idx, q in enumerate(row.get("queries", []))
        ]
        spans = [
            {
                "id":          f"{request_id}-s{idx}",
                "name":        f"{request_id}-s{idx}",
                "method":      s["name"],
                "duration_ms": s["duration_ms"],
                "idx":         idx,
            }
            for idx, s in enumerate(row.get("spans", []))
        ]
        return {
            "id":               request_id,
            "name":             request_id,
            "method":           row["method"],
            "path":             row["path"],
            "status_code":      row["status_code"],
            "duration_ms":      row["duration_ms"],
            "query_count":      row["query_count"],
            "total_query_ms":   row["total_query_ms"],
            "slow_query_count": row["slow_query_count"],
            "slow":             row.get("slow", False),
            "spans":            spans,
            "queries":          queries,
        }
