"""Controller for the ``ScheduledJobState`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class ScheduledJobState(Document):
    """Last run of one scheduled job - written by grunt.tasks.job_log."""

    job_name: str | None
    cron_expression: str | None
    last_status: str | None
    last_started_at: datetime | None
    last_finished_at: datetime | None
    run_count: int | None
    failure_count: int | None
    last_failed_at: datetime | None
    last_error: str | None
