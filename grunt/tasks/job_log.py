"""ScheduledJobLog rows: one per scheduler firing, opened as Running and
closed as Success/Failed - by the scheduler for jobs it runs inline, by
``ScheduledJobLogMiddleware`` in the worker for enqueued TaskIQ tasks."""

from datetime import UTC, datetime, timedelta

from grunt import log
from grunt.db.session import async_session_factory

# TaskIQ label carrying the ScheduledJobLog id from the scheduler to the worker.
LOG_LABEL = "scheduled_job_log"

# A row still Running after this long lost its process (restart, crash).
STALE_AFTER = timedelta(hours=24)


async def open_job_log(job_name: str, cron_expression: str) -> str | None:
    """Insert a Running row. Returns its name, or None if it could not be written."""
    try:
        import grunt

        async with async_session_factory() as session, grunt.system_context(session):
            doc = await grunt.new_doc(
                "ScheduledJobLog",
                {
                    "job_name": job_name,
                    "started_at": datetime.now(UTC),
                    "status": "Running",
                    "cron_expression": cron_expression,
                },
            )
            return str(doc.get("name", ""))
    except Exception as exc:
        log.warning("scheduler.log_write_failed", job_name=job_name, error=str(exc))
        return None


async def close_job_log(log_id: str, *, error: BaseException | str | None = None) -> None:
    """Mark the row Success, or Failed with *error*."""
    values: dict = {"status": "Success", "finished_at": datetime.now(UTC)}
    if error is not None:
        values["status"] = "Failed"
        values["error_message"] = str(error) or type(error).__name__
    try:
        import grunt

        async with async_session_factory() as session, grunt.system_context(session):
            await grunt.db.set_value("ScheduledJobLog", log_id, values)
    except Exception as exc:
        log.warning("scheduler.log_update_failed", log_id=log_id, error=str(exc))


async def fail_stale_job_logs() -> None:
    """Close rows left Running by a process that died mid-job."""
    try:
        import grunt

        async with async_session_factory() as session, grunt.system_context(session):
            await grunt.db.bulk_update(
                "ScheduledJobLog",
                {"status": "Running", "started_at__lt": datetime.now(UTC) - STALE_AFTER},
                {"status": "Failed", "error_message": "Interrupted: the job never finished"},
            )
    except Exception as exc:
        log.warning("scheduler.stale_logs_failed", error=str(exc))
