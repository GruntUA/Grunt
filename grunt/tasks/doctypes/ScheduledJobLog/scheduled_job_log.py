"""Controller for the ``ScheduledJobLog`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class ScheduledJobLog(Document):
    """DocType controller for ScheduledJobLog."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    job_name: str  # Job name
    started_at: datetime  # Start
    finished_at: datetime | None = None  # End
    status: str  # Status
    error_message: str | None = None  # Error
    cron_expression: str | None = None  # Cron expression

    # end: auto-generated types
