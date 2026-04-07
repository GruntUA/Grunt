"""SQL query profiler for dev mode.

Two layers:
  1. Global ring buffer  — last N queries across all requests (always-on in debug mode)
  2. Per-request context — queries grouped by request_id via contextvars

The per-request collector is attached by RequestLoggingMiddleware:

    with collect_for_request(request_id):
        response = await call_next(request)

Results are exposed via /api/v1/dev/profiler.
"""

from __future__ import annotations

import time
import threading
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from typing import Generator

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger()

# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class QueryRecord:
    sql: str
    duration_ms: float
    param_count: int
    slow: bool
    request_id: str | None = None


@dataclass
class RequestProfile:
    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    query_count: int
    slow_query_count: int
    total_query_ms: float
    slow: bool = False
    queries: list[QueryRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ── Global ring buffer (last 200 requests) ────────────────────────────────

_MAX_REQUESTS = 200
_MAX_QUERIES  = 1000  # per ring buffer (across all requests)

_request_buffer: deque[RequestProfile] = deque(maxlen=_MAX_REQUESTS)
_query_buffer:   deque[QueryRecord]    = deque(maxlen=_MAX_QUERIES)
_buffer_lock = threading.Lock()

# ── Runtime settings (mutable via API) ────────────────────────────────────

_profiling_enabled:      bool  = True
_global_threshold_ms:    float = 10.0
_slow_request_db_ms:     float = 20.0
_slow_request_ms:        float = 100.0


def get_settings() -> dict:
    return {
        "enabled": _profiling_enabled,
        "threshold_ms": _global_threshold_ms,
        "slow_request_db_ms": _slow_request_db_ms,
        "slow_request_ms": _slow_request_ms,
    }


def set_enabled(enabled: bool) -> None:
    global _profiling_enabled
    _profiling_enabled = enabled


def set_threshold(threshold_ms: float) -> None:
    global _global_threshold_ms
    _global_threshold_ms = threshold_ms


def set_request_db_threshold(ms: float) -> None:
    global _slow_request_db_ms
    _slow_request_db_ms = ms


def set_request_threshold(ms: float) -> None:
    global _slow_request_ms
    _slow_request_ms = ms

# ── Per-request context ────────────────────────────────────────────────────

# Holds list of QueryRecord being accumulated for the current request
_request_queries: ContextVar[list[QueryRecord] | None] = ContextVar(
    "_request_queries", default=None
)
_request_id_var: ContextVar[str | None] = ContextVar("_request_id_var", default=None)
_threshold_var:  ContextVar[float] = ContextVar("_threshold_var", default=200.0)


@contextmanager
def collect_for_request(
    request_id: str,
    threshold_ms: float = 200.0,
) -> Generator[None, None, None]:
    """Context manager: accumulates queries for *request_id* in a per-request list.

    When profiling is disabled the context manager is a no-op.
    """
    if not _profiling_enabled:
        yield
        return

    queries: list[QueryRecord] = []
    token_q  = _request_queries.set(queries)
    token_id = _request_id_var.set(request_id)
    token_th = _threshold_var.set(_global_threshold_ms)
    try:
        yield
    finally:
        _request_queries.reset(token_q)
        _request_id_var.reset(token_id)
        _threshold_var.reset(token_th)


def finish_request(
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> RequestProfile | None:
    """Called after a request completes — flush per-request queries to ring buffer."""
    queries: list[QueryRecord] | None = _request_queries.get(None)
    if queries is None:
        return None

    slow_count = sum(1 for q in queries if q.slow)
    total_q_ms = sum(q.duration_ms for q in queries)
    is_slow = duration_ms >= _slow_request_ms or total_q_ms >= _slow_request_db_ms

    profile = RequestProfile(
        request_id=request_id,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        query_count=len(queries),
        slow_query_count=slow_count,
        total_query_ms=round(total_q_ms, 2),
        slow=is_slow,
        queries=list(queries),
    )

    with _buffer_lock:
        _request_buffer.appendleft(profile)

    if is_slow:
        logger.warning(
            "slow_request",
            request_id=request_id,
            method=method,
            path=path,
            duration_ms=duration_ms,
            total_query_ms=round(total_q_ms, 2),
            query_count=len(queries),
            slow_query_count=slow_count,
            threshold_request_ms=_slow_request_ms,
            threshold_db_ms=_slow_request_db_ms,
        )

    return profile


# ── Public API for the /dev/profiler endpoint ─────────────────────────────

def get_recent_requests(limit: int = 50) -> list[dict]:
    with _buffer_lock:
        items = list(_request_buffer)[:limit]
    return [p.to_dict() for p in items]


def get_slow_queries(limit: int = 100) -> list[dict]:
    with _buffer_lock:
        items = [asdict(q) for q in _query_buffer if q.slow]
    return items[-limit:]


def clear_buffers() -> None:
    with _buffer_lock:
        _request_buffer.clear()
        _query_buffer.clear()


def get_stats() -> dict:
    with _buffer_lock:
        requests = list(_request_buffer)
        queries  = list(_query_buffer)

    if not requests:
        return {"request_count": 0, "slow_query_count": 0, "avg_duration_ms": 0}

    slow_q = sum(1 for q in queries if q.slow)
    avg_dur = sum(r.duration_ms for r in requests) / len(requests)
    p95_dur = sorted(r.duration_ms for r in requests)[int(len(requests) * 0.95)]

    return {
        "request_count": len(requests),
        "slow_query_count": slow_q,
        "avg_duration_ms": round(avg_dur, 1),
        "p95_duration_ms": round(p95_dur, 1),
    }


# ── SQLAlchemy event hooks ─────────────────────────────────────────────────

def attach_query_profiler(engine: AsyncEngine, threshold_ms: float = 200.0) -> None:
    """Register before/after cursor hooks on *engine*.

    Each executed query is:
      - Added to the per-request list (if inside collect_for_request)
      - Added to the global ring buffer
      - Logged at WARNING if slow
    """
    from sqlalchemy import event  # noqa: PLC0415

    sync = engine.sync_engine

    @event.listens_for(sync, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_query_start", []).append(time.perf_counter())

    @event.listens_for(sync, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        start_times: list[float] = conn.info.get("_query_start", [])
        if not start_times:
            return

        duration_ms = (time.perf_counter() - start_times.pop()) * 1000
        threshold   = _threshold_var.get(_global_threshold_ms)
        is_slow     = duration_ms >= threshold

        sql_preview = statement.strip()

        param_count = len(parameters) if isinstance(parameters, (list, tuple)) else 0
        req_id      = _request_id_var.get(None)

        record = QueryRecord(
            sql=sql_preview,
            duration_ms=round(duration_ms, 2),
            param_count=param_count,
            slow=is_slow,
            request_id=req_id,
        )

        # Per-request accumulation
        per_req = _request_queries.get(None)
        if per_req is not None:
            per_req.append(record)

        # Global ring buffer
        with _buffer_lock:
            _query_buffer.append(record)

        if is_slow:
            logger.warning(
                "slow_query",
                duration_ms=record.duration_ms,
                threshold_ms=threshold,
                sql=sql_preview,
                param_count=param_count,
                request_id=req_id,
            )
