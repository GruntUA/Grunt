"""Controller for the ``ScheduledJobLog`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class ScheduledJobLog(Document):
    """DocType controller for ScheduledJobLog."""

    job_name: str | None
    started_at: datetime | None
    finished_at: datetime | None
    status: str | None
    error_message: str | None
    cron_expression: str | None
