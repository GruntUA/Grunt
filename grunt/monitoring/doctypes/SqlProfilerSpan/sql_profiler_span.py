"""Controller for the ``SqlProfilerSpan`` DocType."""

from grunt.document.base import Document


class SqlProfilerSpan(Document):
    """DocType controller for SqlProfilerSpan."""

    method: str | None
    duration_ms: float | None
