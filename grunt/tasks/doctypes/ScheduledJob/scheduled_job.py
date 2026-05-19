from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from grunt.app import grunt
from grunt.metadata.virtual import VirtualDocType


class ScheduledJobController(VirtualDocType):
    """Virtual DocType controller for Scheduled Jobs (ServerScript with Scheduler Event type)."""

    async def get_list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
        search: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get list of scheduled jobs from ServerScript."""
        rows = await grunt.db.get_all(
            "ServerScript",
            filters={"script_type": "Scheduler Event"},
            fields=["name", "is_enabled", "cron"],
            order_by="name",
            order="asc",
            limit=per_page,
        )

        if search:
            rows = [r for r in rows if search.lower() in str(r.get("name", "")).lower()]

        job_names = [row["name"] for row in rows]
        stats = await self._load_job_stats(job_names)
        items = [_build_job(row, stats.get(row["name"], {})) for row in rows]

        return self.build_response(items, page, per_page)

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get single scheduled job by name."""
        rows = await grunt.db.get_all(
            "ServerScript",
            filters={"name": doc_id, "script_type": "Scheduler Event"},
            fields=["name", "is_enabled", "cron"],
            limit=1,
        )
        if not rows:
            return {}

        stats = await self._load_job_stats([doc_id])
        return _build_job(rows[0], stats.get(doc_id, {}))

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Create new scheduled job via ServerScript."""
        return {
            "name": data.get("name", "new_job"),
            "enabled": data.get("enabled", True),
            "cron_expression": data.get("cron_expression", ""),
            "status": "Pending",
        }

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Update scheduled job via ServerScript."""
        return {
            "name": doc_id,
            "enabled": data.get("enabled", True),
            "cron_expression": data.get("cron_expression", ""),
            "status": "Pending",
        }

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        """Delete scheduled job (deletes ServerScript)."""

    async def _load_job_stats(self, job_names: list[str]) -> dict[str, dict[str, Any]]:
        """Load last execution stats and run counts from ScheduledJobLog."""
        if not job_names:
            return {}

        try:
            logs = await grunt.db.get_all(
                "ScheduledJobLog",
                fields=["job_name", "status", "finished_at", "error_message"],
                order_by="started_at",
                order="desc",
                limit=len(job_names) * 500,
            )
            count_rows = await grunt.db.aggregate(
                "ScheduledJobLog",
                filters={"status": {"__in": ["Success", "Failed"]}},
                group_by="job_name",
                aggregations={"run_count": "count()"},
            )
        except Exception:  # noqa: BLE001
            return {}

        run_counts = {row["job_name"]: row["run_count"] for row in count_rows}

        stats: dict[str, dict[str, Any]] = {}
        for row in logs:
            jn = row.get("job_name")
            if jn not in job_names or jn in stats:
                continue
            status = row.get("status")
            stats[jn] = {
                "status": status,
                "last_run_at": row.get("finished_at"),
                "last_error": row.get("error_message") if status == "Failed" else None,
                "run_count": run_counts.get(jn, 0),
            }

        return stats


def _build_job(row: dict[str, Any], stat: dict[str, Any]) -> dict[str, Any]:
    """Build a ScheduledJob dict from a ServerScript row and execution stats."""
    cron_expr = row.get("cron") or ""
    return {
        "id": row["name"],
        "name": row["name"],
        "enabled": row.get("is_enabled"),
        "cron_expression": cron_expr,
        "next_run_at": _next_run(cron_expr),
        "last_run_at": stat.get("last_run_at"),
        "status": stat.get("status", "Pending"),
        "last_error": stat.get("last_error"),
        "run_count": stat.get("run_count", 0),
        "executor": "server_script",
    }


def _next_run(cron_expr: str) -> datetime | None:
    """Calculate the next fire time for a cron expression."""
    if not cron_expr:
        return None
    try:
        trigger = CronTrigger.from_crontab(cron_expr)
        return trigger.get_next_fire_time(None, datetime.now(UTC))
    except Exception:  # noqa: BLE001
        return None
