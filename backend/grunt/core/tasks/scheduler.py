from __future__ import annotations

import importlib
from typing import Any, Callable, Union

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = structlog.get_logger()

# Global scheduler instance
scheduler = AsyncIOScheduler()


def register_scheduler_events(events: dict[str, list[Union[str, dict]]]) -> None:
    """Register scheduled tasks from a dictionary (e.g. from app's hooks.py).

    Format:
    {
        "all": ["path.to.task", ...],
        "cron": [
            {"handler": "path.to.task", "expression": "0 * * * *"}
        ]
    }
    """
    for event_type, tasks in events.items():
        if not isinstance(tasks, list):
            tasks = [tasks]

        for item in tasks:
            path = item if isinstance(item, str) else item.get("handler")
            
            # Map standard Frappe-like event names to Cron
            cron_expr = None
            if event_type == "all":
                cron_expr = "*/1 * * * *"  # Every minute (or as configured)
            elif event_type == "hourly":
                cron_expr = "0 * * * *"
            elif event_type == "daily":
                cron_expr = "0 0 * * *"
            elif event_type == "weekly":
                cron_expr = "0 0 * * 0"
            elif event_type == "monthly":
                cron_expr = "0 0 1 * *"
            elif event_type == "cron":
                cron_expr = item.get("expression")

            if not cron_expr or not path:
                logger.warning("scheduler.invalid_task", event=event_type, item=item)
                continue

            _add_scheduled_job(path, cron_expr)


def _add_scheduled_job(path: str, cron_expr: str) -> None:
    try:
        module_path, func_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        task_fn = getattr(module, func_name)
        
        # We don't call the task directly, we send it to TaskIQ broker
        # This assumes the function is decorated with @task (wrapped in TaskIQ task)
        
        async def trigger_task():
            logger.info("scheduler.triggering_task", path=path)
            # Use TaskIQ's kiq to send to worker
            await task_fn.kiq()

        scheduler.add_job(
            trigger_task,
            CronTrigger.from_crontab(cron_expr),
            id=path,
            replace_existing=True,
        )
        logger.info("scheduler.job_added", path=path, cron=cron_expr)
        
    except (ImportError, AttributeError, ValueError) as e:
        logger.warning("scheduler.register_failed", path=path, error=str(e))


async def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("scheduler.started")


async def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("scheduler.stopped")
