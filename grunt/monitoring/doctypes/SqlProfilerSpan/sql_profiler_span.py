"""Controller for the ``SqlProfilerSpan`` DocType."""

from grunt.document.base import Document


class SqlProfilerSpan(Document):
    """DocType controller for SqlProfilerSpan."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    method: str | None = None  # Method
    duration_ms: float | None = None  # Time (ms)

    # end: auto-generated types
