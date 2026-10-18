import importlib
from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from grunt import log
from grunt.db.session import async_session_factory
from grunt.email.tasks import send_notification_digest
from grunt.scripting.server_script import ServerScriptRunner
from grunt.tasks.job_log import LOG_LABEL, close_job_log, fail_stale_job_logs, open_job_log

# Global scheduler instance
scheduler = AsyncIOScheduler()

# Handlers from hooks' scheduler_events that could not be registered
# (path -> error) - shown by the «Стан системи» report instead of only a log line.
failed_jobs: dict[str, str] = {}


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

            # Map standard event names to Cron
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
                log.warning("scheduler.invalid_task", event_type=event_type, item=item)
                continue

            _add_scheduled_job(path, cron_expr)


def _add_scheduled_job(path: str, cron_expr: str) -> None:
    try:
        module_path, func_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        task_fn = getattr(module, func_name)

        async def trigger_task():
            log.info("scheduler.triggering_task", path=path)
            await _run_logged(path, cron_expr, task_fn)

        scheduler.add_job(
            trigger_task,
            CronTrigger.from_crontab(cron_expr),
            id=path,
            replace_existing=True,
        )
        failed_jobs.pop(path, None)
        log.info("scheduler.job_added", path=path, cron=cron_expr)

    except (ImportError, AttributeError, ValueError) as e:
        failed_jobs[path] = str(e)
        log.warning("scheduler.register_failed", path=path, error=str(e))


async def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        log.info("scheduler.started")
    await fail_stale_job_logs()
    _register_framework_jobs()
    await _register_server_script_jobs()


def _register_framework_jobs() -> None:
    """Register built-in framework recurring tasks."""
    _add_scheduled_job("grunt.email.tasks.process_email_queue", "*/5 * * * *")  # every 5 min
    _add_scheduled_job("grunt.email.tasks.pull_from_accounts", "*/10 * * * *")  # every 10 min
    _add_scheduled_job("grunt.tasks.auto_repeat.run_auto_repeats", "0 1 * * *")  # 01:00 daily
    _add_scheduled_job("grunt.notification.sla.check_deadlines", "*/10 * * * *")  # every 10 min
    _add_scheduled_job("grunt.notification.date_rules.check_date_rules", "0 8 * * *")  # 08:00
    _add_scheduled_job("grunt.tasks.reminders.send_reminders", "* * * * *")  # every minute

    async def _daily_digest():
        await _run_logged("grunt.digest.daily", "0 8 * * *", send_notification_digest, "daily")

    async def _weekly_digest():
        await _run_logged("grunt.digest.weekly", "0 8 * * 1", send_notification_digest, "weekly")

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

    # Hourly check; the backup itself runs when SystemSettings' interval has passed.
    _add_scheduled_job("grunt.backups.tasks.scheduled_backup", "15 * * * *")
    _add_scheduled_job("grunt.tasks.retention.purge_expired_documents", "0 3 * * *")  # daily 03:00
    _add_scheduled_job("grunt.auth.tasks.close_idle_sessions", "5 * * * *")  # hourly
    _add_scheduled_job("grunt.storage.tasks.collect_garbage", "30 3 * * *")  # daily 03:30
    # Old files into cloud storage (no-op without a StorageRemote «Move old files here»).
    _add_scheduled_job("grunt.storage.cloud.tasks.offload_files", "0 4 * * *")  # daily 04:00
    _add_scheduled_job("grunt.tasks.todo_reminders.send_due_reminders", "0 8 * * *")  # daily 08:00
    _add_scheduled_job("grunt.reports.delivery.send_scheduled_reports", "0 7 * * *")  # daily 07:00

    log.info("scheduler.framework_jobs_registered")


async def _register_server_script_jobs() -> None:
    """Load all enabled Scheduler-Event server scripts from DB and register as cron jobs."""
    try:
        from grunt.db.session import async_session_factory
        from grunt.scripting.server_script import ServerScriptRunner

        runner = ServerScriptRunner()
        async with async_session_factory() as session:
            scripts = await runner.load_scheduler_scripts(session)

        for entry in scripts:
            cron_expr = entry.get("cron") or "0 * * * *"
            script_name = entry["name"]
            script_code = entry["script"]
            _register_server_script_cron(script_name, script_code, cron_expr)

        if scripts:
            log.info("scheduler.server_scripts_loaded", count=len(scripts))
    except Exception as exc:
        log.warning("scheduler.server_scripts_load_failed", error=str(exc))


def _register_server_script_cron(name: str, script: str, cron_expr: str) -> None:
    """Register a single server script as an APScheduler cron job."""

    async def _execute() -> None:
        async with async_session_factory() as session:
            result = await ServerScriptRunner().execute(
                script, session=session, trusted=True, user_email="system"
            )
        if result.output:
            log.debug("scheduler.server_script_output", name=name, output=result.output)

    async def _run() -> None:
        log.info("scheduler.server_script_run", name=name)
        await _run_logged(name, cron_expr, _execute)

    try:
        scheduler.add_job(
            _run,
            CronTrigger.from_crontab(cron_expr),
            id=f"server_script:{name}",
            replace_existing=True,
        )
        log.info("scheduler.server_script_registered", name=name, cron=cron_expr)
    except Exception as exc:
        log.warning("scheduler.server_script_register_failed", name=name, error=str(exc))


async def _run_logged(
    job_name: str, cron_expr: str, task_fn: Callable[..., Awaitable[Any]], *args: Any
) -> None:
    """Run one scheduler firing with a ScheduledJobLog row around it.

    A TaskIQ task is only enqueued here: the row id rides in its labels and
    ``ScheduledJobLogMiddleware`` closes the row once a worker has run it.
    """
    log_id = await open_job_log(job_name, cron_expr)
    kicker = getattr(task_fn, "kicker", None)
    try:
        if kicker is None:
            await task_fn(*args)
        else:
            enqueue = kicker().with_labels(**{LOG_LABEL: log_id}) if log_id else kicker()
            await enqueue.kiq(*args)
            return
    except Exception as exc:
        log.error("scheduler.job_failed", job_name=job_name, error=str(exc))
        if log_id:
            await close_job_log(log_id, error=exc)
        return
    if log_id:
        await close_job_log(log_id)


async def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        log.info("scheduler.stopped")
