"""Performance metrics - per-hour aggregates persisted to ``PerfStat``.

Every measured call (an HTTP route, an RPC method, a document save, a
background task, a ``@profile`` span) is folded into an in-process bucket
keyed by ``(hour, kind, endpoint, ref_doctype)``: call count, errors, total /
max time, SQL queries issued and a fixed-bounds latency histogram (p50/p95
come from it). Nothing touches the database on the hot path.

A background loop (:func:`run_flush_loop`, started by the web server and the
task worker) writes the buckets every :data:`FLUSH_INTERVAL_S` seconds - one
row per key per hour, merged into the row the previous flush wrote. Several
processes merge into the same row, so the hour is complete once every
process has flushed.

``SystemSettings.perf_monitoring_enabled`` turns persisting off (the buckets
are still collected - it costs a dict update per call - but discarded).
"""

import asyncio
import functools
import hashlib
import time
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, event, select
from sqlalchemy.ext.asyncio import AsyncEngine

import grunt
from grunt import log
from grunt.db.write_intent import set_write_intent
from grunt.site.manager import current_site, site_manager
lazy from grunt.site.settings import get_setting

KINDS = ("HTTP", "RPC", "Page", "Document", "Task", "Span")

# Upper bounds (ms) of the histogram buckets; one more bucket catches the rest.
BOUNDS_MS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)
HIST_FIELDS = tuple(f"h_{i}" for i in range(len(BOUNDS_MS) + 1))

FLUSH_INTERVAL_S = 60
# Per site and flush; anything past it is folded into one "(other)" endpoint
# so a route with unbounded names can't flood the table.
MAX_KEYS = 5000
OTHER = "(other)"


@dataclass(slots=True)
class Stat:
    calls: int = 0
    errors: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    sql_calls: int = 0
    sql_ms: float = 0.0
    hist: list[int] = field(default_factory=lambda: [0] * len(HIST_FIELDS))

    def add(self, ms: float, sql_calls: int, sql_ms: float, error: bool) -> None:
        self.calls += 1
        self.errors += error
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)
        self.sql_calls += sql_calls
        self.sql_ms += sql_ms
        self.hist[bucket_of(ms)] += 1


# (hour start as epoch seconds, kind, endpoint, ref_doctype or "")
Key = tuple[int, str, str, str]

_buffers: dict[str, dict[Key, Stat]] = {}


def bucket_of(ms: float) -> int:
    for i, bound in enumerate(BOUNDS_MS):
        if ms <= bound:
            return i
    return len(BOUNDS_MS)


def percentile(hist: list[int], q: float, max_ms: float) -> float | None:
    """Estimate the *q* quantile (0..1) from a histogram, interpolating
    linearly inside the bucket it falls in."""
    total = sum(hist)
    if not total:
        return None
    rank = q * total
    seen = 0
    for i, n in enumerate(hist):
        if n and seen + n >= rank:
            low = BOUNDS_MS[i - 1] if i else 0.0
            high = BOUNDS_MS[i] if i < len(BOUNDS_MS) else max(max_ms, low)
            value = low + (high - low) * (rank - seen) / n
            return round(min(value, max_ms), 2)
        seen += n
    return round(max_ms, 2)


@functools.cache
def _default_site() -> str | None:
    """The site work outside a request runs on (the task worker resolves
    it from ``currentsite.txt``); read once, not per call."""
    try:
        return site_manager.get_active_site()
    except ValueError:
        return None


def record(
    kind: str,
    endpoint: str,
    ms: float,
    *,
    ref_doctype: str | None = None,
    sql: SqlTally | None = None,
    error: bool = False,
) -> None:
    """Add one measured call to the current site's buckets."""
    site = current_site.get(None) or _default_site()
    if not site:
        return
    stats = _buffers.setdefault(site, {})
    hour = int(time.time()) // 3600 * 3600
    key = (hour, kind, endpoint, ref_doctype or "")
    stat = stats.get(key)
    if stat is None:
        if len(stats) >= MAX_KEYS:
            key = (hour, kind, OTHER, "")
            stat = stats.get(key)
        if stat is None:
            stat = stats[key] = Stat()
    stat.add(ms, sql.count if sql else 0, sql.ms if sql else 0.0, error)


# SQL accounting


@dataclass(slots=True)
class SqlTally:
    """Queries issued while a measurement is open. Nested measurements
    (a save inside a request) each count their own and their parents'."""

    count: int = 0
    ms: float = 0.0
    parent: SqlTally | None = None


_sql_tally: ContextVar[SqlTally | None] = ContextVar("perf_sql_tally", default=None)


@contextmanager
def sql_tally() -> Generator[SqlTally]:
    tally = SqlTally(parent=_sql_tally.get())
    token = _sql_tally.set(tally)
    try:
        yield tally
    finally:
        _sql_tally.reset(token)


@contextmanager
def measure(kind: str, endpoint: str, ref_doctype: str | None = None) -> Generator[None]:
    """Time the block and :func:`record` it; an exception counts as an error."""
    start = time.perf_counter()
    error = False
    with sql_tally() as tally:
        try:
            yield
        except Exception:
            error = True
            raise
        finally:
            ms = (time.perf_counter() - start) * 1000
            record(kind, endpoint, ms, ref_doctype=ref_doctype, sql=tally, error=error)


def _before_cursor(conn, cursor, statement, parameters, context, executemany):
    if context is not None and _sql_tally.get() is not None:
        context._perf_start = time.perf_counter()


def _after_cursor(conn, cursor, statement, parameters, context, executemany):
    start = getattr(context, "_perf_start", None)
    if start is None:
        return
    ms = (time.perf_counter() - start) * 1000
    tally = _sql_tally.get()
    while tally is not None:
        tally.count += 1
        tally.ms += ms
        tally = tally.parent


def attach_sql_counter(engine: AsyncEngine) -> None:
    """Count every query on *engine* into the open :class:`SqlTally`, if any.
    Idempotent."""
    sync = engine.sync_engine
    if not event.contains(sync, "before_cursor_execute", _before_cursor):
        event.listen(sync, "before_cursor_execute", _before_cursor)
        event.listen(sync, "after_cursor_execute", _after_cursor)


# Persisting

_MERGED_FIELDS = ("calls", "errors", "total_ms", "max_ms", "sql_calls", "sql_ms", *HIST_FIELDS)


def row_name(key: Key) -> str:
    hour, kind, endpoint, ref_doctype = key
    digest = hashlib.sha1(f"{kind}|{endpoint}|{ref_doctype}".encode()).hexdigest()[:12]
    return f"{datetime.fromtimestamp(hour, UTC):%Y%m%d%H}-{digest}"


def _derived(row: dict[str, Any], hist: list[int]) -> dict[str, Any]:
    """The per-row figures computed from the summed ones."""
    calls = row["calls"] or 1
    return {
        "avg_ms": round(row["total_ms"] / calls, 2),
        "avg_sql": round(row["sql_calls"] / calls, 2),
        "p50_ms": percentile(hist, 0.5, row["max_ms"]),
        "p95_ms": percentile(hist, 0.95, row["max_ms"]),
    }


def _merge(existing: dict[str, Any] | None, key: Key, stat: Stat) -> dict[str, Any]:
    old = existing or {}
    hist = [(old.get(f) or 0) + n for f, n in zip(HIST_FIELDS, stat.hist, strict=True)]
    row = {
        "calls": (old.get("calls") or 0) + stat.calls,
        "errors": (old.get("errors") or 0) + stat.errors,
        "total_ms": round((old.get("total_ms") or 0) + stat.total_ms, 2),
        "max_ms": round(max(old.get("max_ms") or 0, stat.max_ms), 2),
        "sql_calls": (old.get("sql_calls") or 0) + stat.sql_calls,
        "sql_ms": round((old.get("sql_ms") or 0) + stat.sql_ms, 2),
        **dict(zip(HIST_FIELDS, hist, strict=True)),
    }
    row.update(_derived(row, hist))
    if existing is None:
        hour, kind, endpoint, ref_doctype = key
        row.update(
            period_start=datetime.fromtimestamp(hour, UTC),
            kind=kind,
            endpoint=endpoint,
            ref_doctype=ref_doctype or None,
        )
    return row


async def persist(stats: dict[Key, Stat]) -> int:
    """Merge *stats* into ``PerfStat`` on the current session; returns rows
    written. The caller commits."""
    dt = await grunt.get_meta("PerfStat")
    if dt is None:  # not migrated yet
        return 0
    table = dt.table
    session = grunt.get_session()
    names = {row_name(key): key for key in stats}
    cols = [table.c.name, *(table.c[f] for f in _MERGED_FIELDS)]
    existing: dict[str, dict[str, Any]] = {}
    chunk = list(names)
    for i in range(0, len(chunk), 500):
        result = await session.execute(select(*cols).where(table.c.name.in_(chunk[i : i + 500])))
        existing.update({r.name: dict(r._mapping) for r in result})

    now = datetime.now(UTC)
    inserts, updates = [], []
    for name, key in names.items():
        row = _merge(existing.get(name), key, stats[key])
        if name in existing:
            updates.append({"_name": name, **row, "modified_at": now})
        else:
            inserts.append(
                {
                    "name": name,
                    "owner": "system",
                    "created_at": now,
                    "modified_at": now,
                    "modified_by": "system",
                    **row,
                }
            )
    if inserts:
        await session.execute(table.insert(), inserts)
    if updates:
        values = {c: bindparam(c) for c in updates[0] if c != "_name"}
        stmt = table.update().where(table.c.name == bindparam("_name")).values(values)
        await session.execute(stmt, updates)
    return len(inserts) + len(updates)


async def _write_site(site: str, stats: dict[Key, Stat]) -> None:

    token = current_site.set(site)
    try:
        maker = site_manager.get_session_maker(site)
        engine = site_manager.get_engine(site)
        set_write_intent(True)
        async with maker() as session, grunt.system_context(session, engine):
            if await get_setting("perf_monitoring_enabled", True):
                await persist(stats)
                await session.commit()
    finally:
        current_site.reset(token)


async def flush() -> None:
    """Write everything collected so far. A failed site's data is dropped,
    not retried - metrics are best-effort."""
    global _buffers
    pending, _buffers = _buffers, {}
    for site, stats in pending.items():
        if not stats:
            continue
        try:
            await _write_site(site, stats)
        except Exception as e:  # noqa: BLE001 - metrics must never break the process
            log.warning("perf.flush_failed", site=site, keys=len(stats), error=str(e))


async def run_flush_loop() -> None:
    """Flush every :data:`FLUSH_INTERVAL_S` seconds until cancelled, then once more."""
    try:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            await flush()
    finally:
        await asyncio.shield(flush())
