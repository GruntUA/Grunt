from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from grunt.document.base import Document
from grunt.i18n import N_, _
from grunt.log import log
from grunt.progress import job_progress
from grunt.query.query import Query
from grunt.store import DELETE, Unavailable, VirtualStore
from grunt.tasks.redis_introspect import (
    entry_timestamp_ms,
    read_task_info,
    redis_conn,
    s,
    stream_broker,
    unavailable_message,
)
from grunt.utils.sizes import human_size


class BackgroundJobStore(VirtualStore):
    """Live view of in-flight (delivered, not yet acked) Redis Stream entries.

    Read-only except for ``delete``, which acks a stuck entry off the pending
    list - a manual "dismiss" for a job that will never finish on its own.
    """

    capabilities = frozenset({DELETE})
    not_supported_message = N_(
        "BackgroundJob is a live view of the queue — it can't be created or edited"
    )

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        rows, reason = await self._load_all()
        if reason:
            raise Unavailable(unavailable_message(reason))
        return rows

    async def delete(self, name: str, *, before: dict[str, Any]) -> None:
        """Ack the entry - removes it from the pending list without retrying it."""
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
            await conn.xack(sb.queue_name, sb.consumer_group_name, name)

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

                pending = await conn.xpending_range(
                    sb.queue_name, sb.consumer_group_name, min="-", max="+", count=1000
                )

                for entry in pending:
                    message_id = s(entry["message_id"])
                    consumer = s(entry["consumer"])

                    info = await read_task_info(conn, message_id)

                    ts = entry_timestamp_ms(message_id)
                    arguments = (
                        {"args": info.get("args"), "kwargs": info.get("kwargs")} if info else None
                    )

                    rows.append(
                        {
                            "name": message_id,
                            "task_name": info.get("task_name"),
                            "task_id": info.get("task_id"),
                            "consumer": consumer,
                            "queued_at": datetime.fromtimestamp(ts / 1000, tz=UTC) if ts else None,
                            "idle_ms": int(entry["time_since_delivered"]),
                            "delivery_count": int(entry["times_delivered"]),
                            "arguments": arguments,
                        }
                    )
        except Exception as exc:
            log.warning("background_job.list_failed", error=str(exc))
            return [], "unreachable"

        tracked = await job_progress([r["task_id"] for r in rows if r["task_id"]])
        for row in rows:
            row.update(_progress_fields(tracked.get(row["task_id"])))
        return rows, None


class BackgroundJob(Document):
    store_class = BackgroundJobStore


def _progress_fields(state: dict[str, Any] | None) -> dict[str, Any]:
    """The list's progress columns from a ``grunt.progress`` payload (all empty if none)."""
    if not state:
        return {"progress": None, "stage": None, "processed": None, "cancellable": 0}
    stage = state.get("description") or state.get("title")
    if state.get("steps", 0) > 1:
        step = _("Step %(step)s of %(steps)s") % {"step": state["step"], "steps": state["steps"]}
        stage = f"{step} · {stage}" if stage else step
    fmt = human_size if state.get("unit") == "bytes" else str
    count, total = state.get("count", 0), state.get("total", 0)
    return {
        "progress": state.get("percent", 0) if total else None,
        "stage": stage,
        "processed": f"{fmt(count)} / {fmt(total)}" if total else (fmt(count) if count else None),
        "cancellable": int(bool(state.get("cancellable"))),
    }
