"""List-report options beyond plain columns: fixed conditions and date grouping.

* ``conditions`` — ``[{"fieldname", "op", "value"}]`` always applied to the
  report (unlike ``filters_config``, which only offers filters to the viewer).
  Operators use the filter-bar vocabulary; a date value may be relative:
  ``today``, ``today-30``, ``today+7`` (days).
* ``date_group`` on a grouping column — ``day`` / ``month`` / ``quarter`` /
  ``year``: rows are grouped by that period, labelled ``2026-09-23``,
  ``2026-09``, ``2026-Q3``, ``2026``.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Integer, String, cast, func

# Filter-bar operator → build_clauses key suffix.
_OP_SUFFIX = {
    "=": "",
    "!=": "__ne",
    ">": "__gt",
    "<": "__lt",
    ">=": "__gte",
    "<=": "__lte",
    "like": "__ilike",
    "in": "__in",
    "not in": "__nin",
    "is set": "__isnull",
    "is not set": "__isnull",
}
OPERATORS = tuple(_OP_SUFFIX)

DATE_BUCKETS = ("day", "month", "quarter", "year")

_RELATIVE_DATE = re.compile(r"^today(?:([+-])(\d+))?$", re.IGNORECASE)


def _resolve_value(value: Any) -> Any:
    if isinstance(value, str):
        m = _RELATIVE_DATE.match(value.strip())
        if m:
            days = int(m.group(2) or 0) * (-1 if m.group(1) == "-" else 1)
            return (date.today() + timedelta(days=days)).isoformat()
    return value


def compile_conditions(conditions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Each condition as a one-key ``build_clauses`` filter (keys may repeat across
    conditions — e.g. a date range — so they are not merged into one dict)."""
    out: list[dict[str, Any]] = []
    for c in conditions or []:
        field, op = c.get("fieldname"), c.get("op") or "="
        if not field or op not in _OP_SUFFIX:
            continue
        if op in ("is set", "is not set"):
            out.append({f"{field}__isnull": op == "is not set"})
            continue
        value = c.get("value")
        if op in ("in", "not in"):
            items = value if isinstance(value, list) else str(value or "").split(",")
            value = [str(v).strip() for v in items if str(v).strip()]
        else:
            value = _resolve_value(value)
        if value in (None, "", []):
            continue
        out.append({f"{field}{_OP_SUFFIX[op]}": value})
    return out


def date_bucket(column: Any, bucket: str, dialect: str) -> Any:
    """SQL expression labelling *column* with its day / month / quarter / year."""
    if dialect == "postgresql":
        fmt = {"day": "YYYY-MM-DD", "month": "YYYY-MM", "quarter": 'YYYY-"Q"Q', "year": "YYYY"}
        return func.to_char(column, fmt[bucket])
    # SQLite (and anything else with strftime)
    if bucket == "quarter":
        quarter = (cast(func.strftime("%m", column), Integer) + 2) // 3
        return func.strftime("%Y", column).op("||")("-Q").op("||")(cast(quarter, String))
    fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}
    return func.strftime(fmt[bucket], column)
