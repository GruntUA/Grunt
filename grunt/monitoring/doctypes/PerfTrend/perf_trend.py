"""Virtual DocType controller - Performance Trend.

Compares two equal periods of ``PerfStat`` per ``(kind, endpoint,
ref_doctype)``: the last ``period`` days and the ``period`` days before.
Sums come from one ``GROUP BY`` per period; p95 is re-estimated from the
summed histogram buckets, so it is a real p95 of the period, not an average
of hourly ones.

``period`` is a pseudo-filter (1 / 7 / 30 days, default 7) - it picks the
window and is never matched against rows.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.i18n import N_
from grunt.monitoring.perf import HIST_FIELDS, percentile
from grunt.query.query import Query
from grunt.store import VirtualStore
from grunt.store.virtual import equals

_db = GruntDB()  # stateless: reads through the context's session

DEFAULT_PERIOD_DAYS = 7
# Below this many calls in either period the change is noise, not a trend.
MIN_CALLS = 10

_GROUP_BY = ["kind", "endpoint", "ref_doctype"]
_SUMS = {
    "calls": "sum(calls)",
    "errors": "sum(errors)",
    "total_ms": "sum(total_ms)",
    "sql_calls": "sum(sql_calls)",
    "max_ms": "max(max_ms)",
    **{f: f"sum({f})" for f in HIST_FIELDS},
}


def _period_days(value: Any) -> int:
    """The period of a ``period`` filter value, in days."""
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return DEFAULT_PERIOD_DAYS
    try:
        return max(1, int(str(value)))
    except ValueError:
        return DEFAULT_PERIOD_DAYS


async def _summarise(start: datetime, end: datetime) -> dict[tuple, dict[str, Any]]:
    rows = await _db.aggregate(
        "PerfStat",
        filters={"period_start__gte": start, "period_start__lt": end},
        group_by=_GROUP_BY,
        aggregations=_SUMS,
    )
    out = {}
    for r in rows:
        calls = r["calls"] or 0
        if not calls:
            continue
        hist = [int(r[f] or 0) for f in HIST_FIELDS]
        max_ms = float(r["max_ms"] or 0)
        out[(r["kind"], r["endpoint"], r["ref_doctype"])] = {
            "calls": calls,
            "errors": r["errors"] or 0,
            "total_ms": round(float(r["total_ms"] or 0), 2),
            "avg_ms": round(float(r["total_ms"] or 0) / calls, 2),
            "p95_ms": percentile(hist, 0.95, max_ms),
            "avg_sql": round((r["sql_calls"] or 0) / calls, 2),
        }
    return out


def _change(cur: dict[str, Any], prev: dict[str, Any] | None, field: str) -> float | None:
    if not prev or cur["calls"] < MIN_CALLS or prev["calls"] < MIN_CALLS:
        return None
    before, now = prev[field], cur[field]
    if not before:
        return None
    return round((now - before) / before * 100, 1)


def _row_name(kind: str, endpoint: str, ref_doctype: str | None, days: int) -> str:
    digest = hashlib.sha1(f"{kind}|{endpoint}|{ref_doctype or ''}".encode()).hexdigest()[:12]
    return f"{days}d-{digest}"


async def build_rows(days: int, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    span = timedelta(days=days)
    current = await _summarise(now - span, now)
    previous = await _summarise(now - 2 * span, now - span)

    rows = []
    for key, cur in current.items():
        kind, endpoint, ref_doctype = key
        prev = previous.get(key)
        sql_change = None
        if prev and cur["calls"] >= MIN_CALLS and prev["calls"] >= MIN_CALLS:
            sql_change = round(cur["avg_sql"] - prev["avg_sql"], 2)
        rows.append(
            {
                "name": _row_name(kind, endpoint, ref_doctype, days),
                "period": str(days),
                "kind": kind,
                "endpoint": endpoint,
                "ref_doctype": ref_doctype,
                **cur,
                "prev_calls": prev["calls"] if prev else None,
                "prev_avg_ms": prev["avg_ms"] if prev else None,
                "prev_p95_ms": prev["p95_ms"] if prev else None,
                "prev_avg_sql": prev["avg_sql"] if prev else None,
                "avg_change": _change(cur, prev, "avg_ms"),
                "p95_change": _change(cur, prev, "p95_ms"),
                "sql_change": sql_change,
            }
        )
    return rows


class PerfTrendStore(VirtualStore):
    not_supported_message = N_("Performance trend is read-only")

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        name = equals(query, "name")
        if name is not None and "d-" in str(name):
            return await build_rows(int(str(name).split("d-", 1)[0]) or DEFAULT_PERIOD_DAYS)
        return await build_rows(_period_days(equals(query, "period")))


class PerfTrend(Document):
    store_class = PerfTrendStore
