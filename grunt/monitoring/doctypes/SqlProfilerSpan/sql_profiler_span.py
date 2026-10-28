"""Controller for the ``SqlProfilerSpan`` DocType."""

from grunt.document.base import BaseDocument


class SqlProfilerSpan(BaseDocument):
    """DocType controller for SqlProfilerSpan."""

    method: str | None
    duration_ms: float | None
