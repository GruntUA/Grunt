"""The syntax of ``group_by`` and ``aggregates`` entries - what a query
groups and sums by, without any SQL.

``group_by``: a field, ``date(field)`` (calendar day) or a period bucket
``day/month/quarter/year(field)``. ``aggregates``: ``fn(field)`` / ``count()``.
Kept apart from the SQL store so the permission layer can tell which fields a
query reads without depending on how a store runs it.
"""

import re

DATE_BUCKETS = ("day", "month", "quarter", "year")

_AGG_EXPR_RE = re.compile(r"^([a-z_]+)(?:\((.*)\))?$")
# "month(created_at)" / "date(due)" - a group_by entry with a period bucket.
GROUP_FN_RE = re.compile(rf"^(date|{'|'.join(DATE_BUCKETS)})\((.+)\)$", re.IGNORECASE)


def parse_aggregation(expr: str) -> tuple[str, str | None]:
    """An ``aggregates`` entry (``sum(amount)``, ``count()``) as (function, field).

    The field is ``None`` for ``count()`` / ``count``. ``ValueError`` for anything
    else than ``fn(field)`` / ``fn``.
    """
    m = _AGG_EXPR_RE.match(expr.strip().lower())
    if not m:
        raise ValueError(f"Invalid aggregation expression: {expr}")
    fn_name, field = m.groups()
    return fn_name, (field.strip() if field else None)


def group_field(entry: str) -> str:
    """The field a ``group_by`` entry reads (``month(posting_date)`` -> ``posting_date``)."""
    m = GROUP_FN_RE.match(entry.strip())
    return m.group(2).strip() if m else entry.strip()
