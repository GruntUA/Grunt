"""``PerfStat`` controller - hourly timing aggregates.

Rows are written in bulk by :mod:`grunt.monitoring.perf` (straight table
writes, no lifecycle); nobody is granted ``write``/``create``. This class only
gives the record a typed shape.
"""

from datetime import datetime

from grunt.document.base import Document


class PerfStat(Document):
    period_start: datetime
    kind: str
    endpoint: str
    ref_doctype: str | None
    calls: int
    errors: int
    total_ms: float
    avg_ms: float
    p50_ms: float | None
    p95_ms: float | None
    max_ms: float
    sql_calls: int
    avg_sql: float
    sql_ms: float
