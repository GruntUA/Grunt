"""Controller for the ``SqlProfilerQuery`` DocType."""

from grunt.document.base import BaseDocument


class SqlProfilerQuery(BaseDocument):
    """DocType controller for SqlProfilerQuery."""

    sql: str | None
    duration_ms: float | None
    param_count: int | None
    slow: bool | None
    request_id: str | None
