from __future__ import annotations

import importlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Global scheduler instance
scheduler = AsyncIOScheduler()


def register_scheduler_events(events: dict[str, list[str | dict]]) -> None:
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
        # Support dict form for "cron": {"expr": ["handler", ...]} as well as list form
        if event_type == "cron" and isinstance(tasks, dict):
            expanded: list = []
            for expr, handlers in tasks.items():
                if isinstance(handlers, str):
                    handlers = [handlers]
                for h in handlers:
                    expanded.append({"handler": h, "expression": expr})
            tasks = expanded

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
                cron_expr = item.get("expression") if isinstance(item, dict) else None

            if not cron_expr or not path:
                logger.warning("scheduler.invalid_task", event_type=event_type, item=item)
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
            if hasattr(task_fn, "kiq"):
                # TaskIQ-decorated task — send to worker
                await task_fn.kiq()
            else:
                # Plain async function — call directly
                await task_fn()

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
    _register_framework_jobs()
    await _register_server_script_jobs()


def _register_framework_jobs() -> None:
    """Register built-in framework recurring tasks."""
    _add_scheduled_job("grunt.core.email.tasks.process_email_queue", "*/5 * * * *")  # every 5 min
    _add_scheduled_job("grunt.core.email.tasks.pull_from_accounts", "*/10 * * * *")  # every 10 min

    async def _daily_digest():
        from grunt.core.email.tasks import send_notification_digest  # noqa: PLC0415

        await send_notification_digest.kiq(period="daily")

    async def _weekly_digest():
        from grunt.core.email.tasks import send_notification_digest  # noqa: PLC0415

        await send_notification_digest.kiq(period="weekly")

    scheduler.add_job(
        _daily_digest,
        CronTrigger.from_crontab("0 8 * * *"),
        id="grunt.digest.daily",
        replace_existing=True,
    )
    scheduler.add_job(
        _weekly_digest,
        CronTrigger.from_crontab("0 8 * * 1"),
        id="grunt.digest.weekly",
        replace_existing=True,
    )
    logger.info("scheduler.framework_jobs_registered")


async def _register_server_script_jobs() -> None:
    """Load all enabled Scheduler-Event server scripts from DB and register as cron jobs."""
    try:
        from grunt.core.db.session import async_session_factory  # noqa: PLC0415
        from grunt.core.scripting.server_script import ServerScriptRunner  # noqa: PLC0415

        runner = ServerScriptRunner()
        async with async_session_factory() as session:
            scripts = await runner.load_scheduler_scripts(session)

        for entry in scripts:
            cron_expr = entry.get("cron") or "0 * * * *"
            script_name = entry["name"]
            script_code = entry["script"]
            _register_server_script_cron(script_name, script_code, cron_expr)

        if scripts:
            logger.info("scheduler.server_scripts_loaded", count=len(scripts))
    except Exception as exc:
        logger.warning("scheduler.server_scripts_load_failed", error=str(exc))


def _register_server_script_cron(name: str, script: str, cron_expr: str) -> None:
    """Register a single server script as an APScheduler cron job."""
    from grunt.core.db.session import async_session_factory  # noqa: PLC0415
    from grunt.core.scripting.server_script import ServerScriptRunner  # noqa: PLC0415

    async def _run() -> None:
        logger.info("scheduler.server_script_run", name=name)
        log_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        async with async_session_factory() as session:
            await _write_job_log(
                session,
                log_id=log_id,
                job_name=name,
                started_at=started_at,
                status="Running",
                cron_expression=cron_expr,
            )

        try:
            async with async_session_factory() as session:
                runner = ServerScriptRunner()
                result = await runner.execute(
                    script, session=session, trusted=True, user_email="system"
                )
            if result.output:
                logger.debug("scheduler.server_script_output", name=name, output=result.output)

            async with async_session_factory() as session:
                await _update_job_log(session, log_id=log_id, status="Success")

        except Exception as exc:
            logger.error("scheduler.server_script_error", name=name, error=str(exc))
            async with async_session_factory() as session:
                await _update_job_log(
                    session, log_id=log_id, status="Failed", error_message=str(exc)
                )

    try:
        scheduler.add_job(
            _run,
            CronTrigger.from_crontab(cron_expr),
            id=f"server_script:{name}",
            replace_existing=True,
        )
        logger.info("scheduler.server_script_registered", name=name, cron=cron_expr)
    except Exception as exc:
        logger.warning("scheduler.server_script_register_failed", name=name, error=str(exc))


async def _write_job_log(
    session: AsyncSession,
    *,
    log_id: str,
    job_name: str,
    started_at: datetime,
    status: str,
    cron_expression: str,
) -> None:
    """Insert a new ScheduledJobLog record via Grunt ORM."""
    try:
        from grunt.app import grunt  # noqa: PLC0415
        from grunt.core.doctypes.user.user import SYSTEM_USER  # noqa: PLC0415

        async with grunt.context(session, None, SYSTEM_USER):
            await grunt.new_doc(
                "ScheduledJobLog",
                {
                    "id": log_id,
                    "job_name": job_name,
                    "started_at": started_at,
                    "status": status,
                    "cron_expression": cron_expression,
                },
            )
    except Exception as exc:
        logger.warning("scheduler.log_write_failed", job_name=job_name, error=str(exc))


async def _update_job_log(
    session: AsyncSession,
    *,
    log_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update a ScheduledJobLog record after job completion via Grunt ORM."""
    try:
        from grunt.app import grunt  # noqa: PLC0415
        from grunt.core.doctypes.user.user import SYSTEM_USER  # noqa: PLC0415

        values: dict = {"status": status, "finished_at": datetime.now(UTC)}
        if error_message is not None:
            values["error_message"] = error_message

        async with grunt.context(session, None, SYSTEM_USER):
            await grunt.db.set_value("ScheduledJobLog", log_id, values)
    except Exception as exc:
        logger.warning("scheduler.log_update_failed", log_id=log_id, error=str(exc))


async def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("scheduler.stopped")
