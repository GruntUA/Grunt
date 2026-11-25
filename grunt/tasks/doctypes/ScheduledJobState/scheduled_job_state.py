"""Controller for the ``ScheduledJobState`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class ScheduledJobState(Document):
    """Last run of one scheduled job - written by grunt.tasks.job_log."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    job_name: str  # Job name
    cron_expression: str | None = None  # Cron expression
    last_status: str | None = None  # Last status
    last_started_at: datetime | None = None  # Last start
    last_finished_at: datetime | None = None  # Last end
    run_count: int | None = None  # Runs
    failure_count: int | None = None  # Failures
    last_failed_at: datetime | None = None  # Last failure
    last_error: str | None = None  # Last error

    # end: auto-generated types
