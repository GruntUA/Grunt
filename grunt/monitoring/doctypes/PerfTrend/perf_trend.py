"""Virtual DocType controller - Performance Trend.

Compares two equal periods of ``PerfStat`` per ``(kind, endpoint,
ref_doctype)``: the last ``period`` days and the ``period`` days before.
Sums come from one ``GROUP BY`` per period; p95 is re-estimated from the
summed histogram buckets, so it is a real p95 of the period, not an average
of hourly ones.

``period`` is a pseudo-filter (1 / 7 / 30 days, default 7) - it picks the
window and is never matched against rows.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import grunt
from grunt import _
from grunt.db.filters import split_key
from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import apply_filters, apply_search, apply_sort, build_response
from grunt.errors import not_found
from grunt.i18n import N_
from grunt.monitoring.perf import HIST_FIELDS, percentile

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


def _period_days(filters: dict[str, Any]) -> int:
    for key in list(filters):
        if split_key(key)[0] == "period":
            value = filters.pop(key)
            if isinstance(value, list):
                value = value[0] if value else ""
            try:
                return max(1, int(str(value)))
            except ValueError:
                break
    return DEFAULT_PERIOD_DAYS


async def _summarise(start: datetime, end: datetime) -> dict[tuple, dict[str, Any]]:
    rows = await grunt.db.aggregate(
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


class PerfTrend(BaseDocument):
    not_supported_message = N_("Performance trend is read-only")

    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "p95_change",
        sort_order: str = "desc",
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        **kwargs: Any,
    ) -> DocumentList:
        filters = dict(filters or {})
        rows = await build_rows(_period_days(filters))

        if search:
            rows = apply_search(rows, search, ["endpoint", "ref_doctype"])
        if filters:
            rows = apply_filters(rows, filters)
        rows = apply_sort(rows, sort_by, sort_order)
        return build_response(rows, page, per_page)

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        days = int(str(self.name).split("d-", 1)[0]) if "d-" in str(self.name) else 0
        for row in await build_rows(days or DEFAULT_PERIOD_DAYS):
            if row["name"] == self.name:
                self.data = row
                return
        raise not_found(_("Performance trend “%(name)s” not found") % {"name": self.name})
