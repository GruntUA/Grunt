from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from grunt.log import log
from grunt.metadata.virtual import VirtualDocType
from grunt.tasks.redis_introspect import redis_conn, s, stream_broker


class BackgroundWorkerController(VirtualDocType):
    """Live view of the TaskIQ consumer group's members (``XINFO CONSUMERS``).

    Read-only except for ``delete``, which drops a dead consumer's
    registration (``XGROUP DELCONSUMER``) — for a worker process that
    crashed and left an idle entry behind.
    """

    async def get_list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "name",
        sort_order: str = "asc",
        search: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        rows = await self._load_all()

        if search:
            rows = self.apply_search(rows, search, ["name"])
        if filters:
            rows = self.apply_filters(rows, filters)
        rows = self.apply_sort(rows, sort_by, sort_order)

        return self.build_response(rows, page, per_page)

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        for row in await self._load_all():
            if row["name"] == doc_id:
                return row
        return {}

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        sb = stream_broker()
        if sb is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Redis broker not configured"
            )
        async with redis_conn() as conn:
            if conn is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Redis unavailable"
                )
            await conn.xgroup_delconsumer(sb.queue_name, sb.consumer_group_name, doc_id)

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail="BackgroundWorker is a live view of the consumer group — it can't be created",
        )

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail="BackgroundWorker is a live view of the consumer group — it can't be edited",
        )

    async def _load_all(self) -> list[dict[str, Any]]:
        sb = stream_broker()
        if sb is None:
            return []

        rows: list[dict[str, Any]] = []
        try:
            async with redis_conn() as conn:
                if conn is None:
                    return []

                consumers = await conn.xinfo_consumers(sb.queue_name, sb.consumer_group_name)
                for c in consumers:
                    inactive = c.get("inactive")
                    rows.append(
                        {
                            "name": s(c.get("name")),
                            "pending": int(c.get("pending", 0)),
                            "idle_ms": int(c.get("idle", 0)),
                            "inactive_ms": int(inactive) if inactive is not None else None,
                        }
                    )
        except Exception as exc:
            log.warning("background_worker.list_failed", error=str(exc))
            return []

        return rows
