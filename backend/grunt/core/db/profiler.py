"""SQL query profiler for dev mode.

Attaches SQLAlchemy cursor events to log slow queries.
Enable via DEBUG=true + optional SLOW_QUERY_THRESHOLD_MS in .env.
"""

from __future__ import annotations

import time

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger()


def attach_query_profiler(engine: AsyncEngine, threshold_ms: float = 200.0) -> None:
    """Register before/after cursor hooks on *engine* to log slow queries.

    Queries that take longer than *threshold_ms* are logged at WARNING level
    with duration, truncated SQL, and parameter count.
    """
    from sqlalchemy import event  # noqa: PLC0415

    sync = engine.sync_engine

    @event.listens_for(sync, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[misc]
        conn.info.setdefault("_query_start", []).append(time.perf_counter())

    @event.listens_for(sync, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # type: ignore[misc]
        start_times: list[float] = conn.info.get("_query_start", [])
        if not start_times:
            return
        duration_ms = (time.perf_counter() - start_times.pop()) * 1000
        if duration_ms >= threshold_ms:
            # Truncate long SQL so logs stay readable
            sql_preview = statement.strip().replace("\n", " ")
            if len(sql_preview) > 400:
                sql_preview = sql_preview[:400] + "…"
            param_count = len(parameters) if isinstance(parameters, (list, tuple)) else 0
            logger.warning(
                "slow_query",
                duration_ms=round(duration_ms, 1),
                threshold_ms=threshold_ms,
                sql=sql_preview,
                param_count=param_count,
            )
