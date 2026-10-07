from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger

import grunt
from grunt import _
from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import build_response
from grunt.errors import not_found
from grunt.i18n import N_


class ScheduledJobController(BaseDocument):
    """Scheduled Jobs - ServerScripts of the Scheduler Event type.

    No insert or update: the underlying ServerScript row also requires a
    `script` body, which this view never collects - create or edit the
    ServerScript itself (script_type="Scheduler Event").
    """

    not_supported_message = N_(
        "Create or edit a ServerScript with script_type='Scheduler Event' instead"
    )

    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        page: int = 1,
        per_page: int = 50,
        search: str | None = None,
        **kwargs: Any,
    ) -> DocumentList:
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
        stats = await cls._load_job_stats(job_names)
        items = [_build_job(row, stats.get(row["name"], {})) for row in rows]

        return build_response(items, page, per_page)

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        """Get single scheduled job by name."""
        name = str(self.name)
        rows = await grunt.db.get_all(
            "ServerScript",
            filters={"name": name, "script_type": "Scheduler Event"},
            fields=["name", "is_enabled", "cron"],
            limit=1,
        )
        if not rows:
            raise not_found(_("Scheduled job “%(name)s” not found") % {"name": name})

        stats = await self._load_job_stats([name])
        self.data = _build_job(rows[0], stats.get(name, {}))

    async def db_delete(self) -> None:
        """Delete scheduled job by deleting the underlying ServerScript."""
        await grunt.delete_doc("ServerScript", str(self.name))

    @staticmethod
    async def _load_job_stats(job_names: list[str]) -> dict[str, dict[str, Any]]:
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
        except Exception:
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
    except Exception:
        return None
