from datetime import UTC, datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger

import grunt
from grunt.document.base import Document
from grunt.i18n import N_
from grunt.query.query import Query
from grunt.store import DELETE, VirtualStore
from grunt.store.virtual import equals


class ScheduledJobStore(VirtualStore):
    """Scheduled Jobs - ServerScripts of the Scheduler Event type.

    No insert or update: the underlying ServerScript row also requires a
    `script` body, which this view never collects - create or edit the
    ServerScript itself (script_type="Scheduler Event").
    """

    capabilities = frozenset({DELETE})
    not_supported_message = N_(
        "Create or edit a ServerScript with script_type='Scheduler Event' instead"
    )

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"script_type": "Scheduler Event"}
        if (name := equals(query, "name")) is not None:
            filters["name"] = name
        scripts = await grunt.db.get_all(
            "ServerScript",
            filters=filters,
            fields=["name", "is_enabled", "cron"],
            order_by="name",
            order="asc",
            limit=None,
        )
        stats = await self._load_job_stats([row["name"] for row in scripts])
        return [_build_job(row, stats.get(row["name"], {})) for row in scripts]

    async def delete(self, name: str, *, before: dict[str, Any]) -> None:
        """Delete scheduled job by deleting the underlying ServerScript."""
        await grunt.delete_doc("ServerScript", name)

    @staticmethod
    async def _load_job_stats(job_names: list[str]) -> dict[str, dict[str, Any]]:
        """Last run and run count of each job, from ScheduledJobState."""
        if not job_names:
            return {}
        try:
            rows = await grunt.db.get_all(
                "ScheduledJobState",
                filters={"name__in": job_names},
                fields=["name", "last_status", "last_finished_at", "last_error", "run_count"],
                limit=None,
            )
        except Exception:
            return {}
        return {
            row["name"]: {
                "status": row.get("last_status"),
                "last_run_at": row.get("last_finished_at"),
                "last_error": row.get("last_error") if row.get("last_status") == "Failed" else None,
                "run_count": row.get("run_count") or 0,
            }
            for row in rows
        }


class ScheduledJob(Document):
    store_class = ScheduledJobStore


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
