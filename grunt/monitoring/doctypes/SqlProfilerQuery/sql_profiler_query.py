"""Controller for the ``SqlProfilerQuery`` DocType."""

from grunt.document.base import Document


class SqlProfilerQuery(Document):
    """DocType controller for SqlProfilerQuery."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    sql: str | None = None  # SQL
    duration_ms: float | None = None  # Time (ms)
    param_count: int | None = None  # Parameters
    slow: bool | None = None  # Slow
    request_id: str | None = None  # Request ID

    # end: auto-generated types
