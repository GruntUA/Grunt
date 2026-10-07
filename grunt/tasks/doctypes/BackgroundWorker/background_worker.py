from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from grunt import _, log
from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import apply_filters, apply_search, apply_sort, build_response
from grunt.errors import not_found
from grunt.i18n import N_
from grunt.tasks.redis_introspect import redis_conn, s, stream_broker, unavailable_message


class BackgroundWorkerController(BaseDocument):
    """Live view of the TaskIQ consumer group's members (``XINFO CONSUMERS``).

    Read-only except for ``delete``, which drops a dead consumer's
    registration (``XGROUP DELCONSUMER``) - for a worker process that
    crashed and left an idle entry behind.
    """

    not_supported_message = N_(
        "BackgroundWorker is a live view of the consumer group — it can't be created or edited"
    )

    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "name",
        sort_order: str = "asc",
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        **kwargs: Any,
    ) -> DocumentList:
        rows, reason = await cls._load_all()

        if search:
            rows = apply_search(rows, search, ["name"])
        if filters:
            rows = apply_filters(rows, filters)
        rows = apply_sort(rows, sort_by, sort_order)

        extra_meta = (
            {"unavailable": True, "unavailable_message": unavailable_message(reason)}
            if reason
            else None
        )
        return build_response(rows, page, per_page, extra_meta=extra_meta)

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        rows, _reason = await self._load_all()
        for row in rows:
            if row["name"] == self.name:
                self.data = row
                return
        raise not_found(_("“%(name)s” not found") % {"name": self.name})

    async def db_delete(self) -> None:
        sb = stream_broker()
        if sb is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_("Redis broker not configured")
            )
        async with redis_conn() as conn:
            if conn is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=_("Redis unavailable")
                )
            await conn.xgroup_delconsumer(sb.queue_name, sb.consumer_group_name, str(self.name))

    @staticmethod
    async def _load_all() -> tuple[list[dict[str, Any]], str | None]:
        """Returns ``(rows, unavailable_reason)`` - reason is ``None`` on a genuine empty list."""
        sb = stream_broker()
        if sb is None:
            return [], "not_configured"

        rows: list[dict[str, Any]] = []
        try:
            async with redis_conn() as conn:
                if conn is None:
                    return [], "not_configured"

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
            return [], "unreachable"

        return rows, None
