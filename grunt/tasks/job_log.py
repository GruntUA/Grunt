"""What a scheduler firing leaves behind.

* ``ScheduledJobState`` - one row per job, updated on every run: last start,
  end, status and error, run and failure counts.
* ``ScheduledJobLog`` - one row per run, opened as Running and closed as
  Success/Failed - but only for jobs that fire at most hourly. A job that
  fires more often (``* * * * *``, ``*/5 * * * *``) mostly finds nothing to
  do; it gets a row only when it fails, else the log is all such runs (as
  in Frappe, where the frequent "All" events are not logged either).
  ``log_runs`` in ``scheduler_events`` overrides this.

The scheduler finishes the jobs it runs inline; for enqueued TaskIQ tasks
the labels below carry the run to the worker, where
``ScheduledJobLogMiddleware`` finishes it.
"""

from datetime import UTC, datetime, timedelta

from grunt import log
from grunt.db.session import async_session_factory
from grunt.db.write_intent import write_intent

# TaskIQ labels carrying a run from the scheduler to the worker.
LOG_LABEL = "scheduled_job_log"  # id of the open ScheduledJobLog row, if any
JOB_LABEL = "scheduled_job"
CRON_LABEL = "scheduled_job_cron"
STARTED_LABEL = "scheduled_job_started"

# A row still Running after this long lost its process (restart, crash).
STALE_AFTER = timedelta(hours=24)


def logs_every_run(cron_expression: str, log_runs: bool | None = None) -> bool:
    """Whether every run of the job gets a ScheduledJobLog row, not only failures.

    By default yes for a job that fires at most hourly - a single number in
    the minute field (``15 * * * *``, ``0 8 * * *``) - and no for one that
    fires several times an hour (``*``, ``*/5``, ``0,30``, ``0-10``).
    """
    if log_runs is not None:
        return log_runs
    fields = cron_expression.split()
    return bool(fields) and fields[0].isdigit()


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


async def finish_job(
    job_name: str | None,
    cron_expression: str,
    started_at: datetime,
    log_id: str | None = None,
    *,
    error: BaseException | str | None = None,
) -> None:
    """Record the end of one run.

    Closes its open ScheduledJobLog row, or - for a run without one - writes
    a Failed row if it failed; then updates the job's ScheduledJobState.
    Separate transactions: a failed state update does not lose the log row.
    """
    import grunt

    now = datetime.now(UTC)
    message = None if error is None else (str(error) or type(error).__name__)
    try:
        async with async_session_factory() as session, grunt.system_context(session):
            if log_id:
                values: dict = {"status": "Success", "finished_at": now}
                if message is not None:
                    values.update(status="Failed", error_message=message)
                await grunt.db.set_value("ScheduledJobLog", log_id, values)
            elif job_name and message is not None:
                await grunt.new_doc(
                    "ScheduledJobLog",
                    {
                        "job_name": job_name,
                        "started_at": started_at,
                        "finished_at": now,
                        "status": "Failed",
                        "error_message": message,
                        "cron_expression": cron_expression,
                    },
                )
    except Exception as exc:
        log.warning("scheduler.log_update_failed", job_name=job_name, error=str(exc))
    if not job_name:
        return
    try:
        async with async_session_factory() as session, grunt.system_context(session):
            await _update_state(job_name, cron_expression, started_at, now, message)
    except Exception as exc:
        log.warning("scheduler.state_update_failed", job_name=job_name, error=str(exc))


async def _update_state(
    job_name: str,
    cron_expression: str,
    started_at: datetime,
    finished_at: datetime,
    error: str | None,
) -> None:
    import grunt

    counts = await grunt.db.get_value(
        "ScheduledJobState", job_name, ["run_count", "failure_count"], as_dict=True
    )
    run_count = (counts.get("run_count") or 0) if counts else 0
    failure_count = (counts.get("failure_count") or 0) if counts else 0
    values: dict = {
        "cron_expression": cron_expression,
        "last_status": "Success" if error is None else "Failed",
        "last_started_at": started_at,
        "last_finished_at": finished_at,
        "run_count": run_count + 1,
        "failure_count": failure_count + (error is not None),
    }
    if error is not None:
        values.update(last_failed_at=finished_at, last_error=error)
    if counts is None:
        await grunt.new_doc("ScheduledJobState", {"job_name": job_name, **values})
    else:
        await grunt.db.set_value("ScheduledJobState", job_name, values)


async def fail_stale_job_logs() -> None:
    """Close rows left Running by a process that died mid-job."""
    try:
        import grunt

        with write_intent():
            async with async_session_factory() as session, grunt.system_context(session):
                await grunt.db.bulk_update(
                    "ScheduledJobLog",
                    {"status": "Running", "started_at__lt": datetime.now(UTC) - STALE_AFTER},
                    {"status": "Failed", "error_message": "Interrupted: the job never finished"},
                )
    except Exception as exc:
        log.warning("scheduler.stale_logs_failed", error=str(exc))
