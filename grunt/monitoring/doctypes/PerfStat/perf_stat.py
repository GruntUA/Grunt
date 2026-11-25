"""``PerfStat`` controller - hourly timing aggregates.

Rows are written in bulk by :mod:`grunt.monitoring.perf` (straight table
writes, no lifecycle); nobody is granted ``write``/``create``. This class only
gives the record a typed shape.
"""

from datetime import datetime

from grunt.document.base import Document


class PerfStat(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    period_start: datetime | None = None  # Hour
    kind: str | None = None  # Kind
    endpoint: str | None = None  # Endpoint
    ref_doctype: str | None = None  # DocType
    calls: int | None = None  # Calls
    errors: int | None = None  # Errors
    total_ms: float | None = None  # Total, ms
    avg_ms: float | None = None  # Average, ms
    p50_ms: float | None = None  # Median, ms
    p95_ms: float | None = None  # p95, ms
    max_ms: float | None = None  # Max, ms
    sql_calls: int | None = None  # SQL queries
    avg_sql: float | None = None  # SQL per call
    sql_ms: float | None = None  # SQL time, ms
    h_0: int | None = None  # ≤ 5 ms
    h_1: int | None = None  # ≤ 10 ms
    h_2: int | None = None  # ≤ 25 ms
    h_3: int | None = None  # ≤ 50 ms
    h_4: int | None = None  # ≤ 100 ms
    h_5: int | None = None  # ≤ 250 ms
    h_6: int | None = None  # ≤ 500 ms
    h_7: int | None = None  # ≤ 1 s
    h_8: int | None = None  # ≤ 2.5 s
    h_9: int | None = None  # ≤ 5 s
    h_10: int | None = None  # ≤ 10 s
    h_11: int | None = None  # > 10 s

    # end: auto-generated types
