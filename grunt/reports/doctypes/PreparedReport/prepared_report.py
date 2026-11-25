"""PreparedReport controller - a result goes with its file."""

from datetime import datetime
from typing import Any

from grunt.document.base import Document
lazy from grunt.document.api import documents


class PreparedReport(Document):
    """DocType controller for PreparedReport (see :mod:`grunt.reports.prepared`)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    report: str | None = None  # Report
    user: str | None = None  # User
    status: str | None = None  # Status
    filters: Any | None = None  # Filters
    filters_hash: str | None = None  # Filters hash
    started_at: datetime | None = None  # Started at
    finished_at: datetime | None = None  # Finished at
    rows: int | None = None  # Rows
    time_ms: int | None = None  # Time, ms
    result_file: str | None = None  # Result file
    error: str | None = None  # Error

    # end: auto-generated types

    async def after_delete(self) -> None:
        if self.result_file:
            # The file is the system's, not the viewer's to delete.
            await documents.delete_doc("File", self.result_file, ignore_permissions=True)
