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

import functools
import inspect
import threading
import time
from collections import deque
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from grunt.log import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


F = TypeVar("F", bound=Callable[..., Any])

# ── Data structures ────────────────────────────────────────────────────────


@dataclass
class QueryRecord:
    sql: str
    duration_ms: float
    param_count: int
    slow: bool
    request_id: str | None = None


@dataclass
class SpanRecord:
    """One named code span (method call, service operation, etc.)."""

    name: str
    duration_ms: float


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
    spans: list[SpanRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ── Global ring buffer (last 200 requests) ────────────────────────────────

_MAX_REQUESTS = 200
_MAX_QUERIES = 1000  # per ring buffer (across all requests)

_request_buffer: deque[RequestProfile] = deque(maxlen=_MAX_REQUESTS)
_query_buffer: deque[QueryRecord] = deque(maxlen=_MAX_QUERIES)
_buffer_lock = threading.Lock()

# ── Runtime settings (mutable via API) ────────────────────────────────────


@dataclass
class _ProfilerSettings:
    enabled: bool = True
    threshold_ms: float = 10.0
    slow_request_db_ms: float = 20.0
    slow_request_ms: float = 100.0
    # N+1 detector: warn when a single request fires more than this many SQL queries
    n1_threshold: int = 10


_settings = _ProfilerSettings()


def get_settings() -> dict:
    return asdict(_settings)


def set_enabled(enabled: bool) -> None:
    _settings.enabled = enabled


def set_threshold(threshold_ms: float) -> None:
    _settings.threshold_ms = threshold_ms


def set_request_db_threshold(ms: float) -> None:
    _settings.slow_request_db_ms = ms


def set_request_threshold(ms: float) -> None:
    _settings.slow_request_ms = ms


def set_n1_threshold(n: int) -> None:
    _settings.n1_threshold = max(1, n)


def get_n1_threshold() -> int:
    return _settings.n1_threshold


# ── Per-request context ────────────────────────────────────────────────────

# Holds list of QueryRecord being accumulated for the current request
_request_queries: ContextVar[list[QueryRecord] | None] = ContextVar(
    "_request_queries", default=None
)
_request_spans: ContextVar[list[SpanRecord] | None] = ContextVar("_request_spans", default=None)
_request_id_var: ContextVar[str | None] = ContextVar("_request_id_var", default=None)
_threshold_var: ContextVar[float] = ContextVar("_threshold_var", default=200.0)


@contextmanager
def collect_for_request(
    request_id: str,
    threshold_ms: float = 200.0,
) -> Generator[None]:
    """Context manager: accumulates queries and spans for *request_id*.

    When profiling is disabled the context manager is a no-op.
    """
    if not _settings.enabled:
        yield
        return

    queries: list[QueryRecord] = []
    spans: list[SpanRecord] = []
    token_q = _request_queries.set(queries)
    token_sp = _request_spans.set(spans)
    token_id = _request_id_var.set(request_id)
    token_th = _threshold_var.set(_settings.threshold_ms)
    try:
        yield
    finally:
        _request_queries.reset(token_q)
        _request_spans.reset(token_sp)
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
    is_slow = duration_ms >= _settings.slow_request_ms or total_q_ms >= _settings.slow_request_db_ms

    spans: list[SpanRecord] = _request_spans.get(None) or []

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
        spans=list(spans),
    )

    with _buffer_lock:
        _request_buffer.appendleft(profile)

    if is_slow:
        log.warning(
            "slow_request",
            request_id=request_id,
            method=method,
            path=path,
            duration_ms=duration_ms,
            total_query_ms=round(total_q_ms, 2),
            query_count=len(queries),
            slow_query_count=slow_count,
            threshold_request_ms=_settings.slow_request_ms,
            threshold_db_ms=_settings.slow_request_db_ms,
        )

    # N+1 detector: warn if more SQL queries than the threshold fired for one request
    if len(queries) > _settings.n1_threshold:
        log.warning(
            "n1_suspect",
            request_id=request_id,
            method=method,
            path=path,
            query_count=len(queries),
            n1_threshold=_settings.n1_threshold,
            hint="Consider using select_related / batch loading to reduce query count",
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
        queries = list(_query_buffer)

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
    from sqlalchemy import event

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
        threshold = _threshold_var.get(_settings.threshold_ms)
        is_slow = duration_ms >= threshold

        sql_preview = statement.strip()

        param_count = len(parameters) if isinstance(parameters, (list, tuple)) else 0
        req_id = _request_id_var.get(None)

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

        # Only warn about slow queries within an HTTP request context;
        # background tasks inherit low thresholds but run outside requests.
        if is_slow and req_id is not None:
            log.warning(
                "slow_query",
                duration_ms=record.duration_ms,
                threshold_ms=threshold,
                sql=sql_preview,
                param_count=param_count,
                request_id=req_id,
            )


# ── Method span profiling ──────────────────────────────────────────────────


@asynccontextmanager
async def profile_span(name: str) -> AsyncGenerator[None]:
    """Async context manager that records a named span in the current request profile.

    Usage::

        async with profile_span("grunt.get_doc"):
            doc = await session.execute(...)
    """
    if not _settings.enabled:
        yield
        return

    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        spans = _request_spans.get(None)
        if spans is not None:
            spans.append(SpanRecord(name=name, duration_ms=round(duration_ms, 2)))


def profile(name: str) -> Callable[[F], F]:
    """Decorator that wraps an async function with a named profiling span.

    Usage::

        @profile("grunt.db.get_all")
        async def get_all(self, doctype, ...):
            ...
    """

    def decorator(fn: F) -> F:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"@profile can only wrap async functions, got {fn!r}")

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with profile_span(name):
                return await fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
