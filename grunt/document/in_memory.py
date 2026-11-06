"""Lists of documents held in memory - for controllers whose source is not a
table (a ring buffer, an API response, Redis).

``apply_filters`` takes the same ``field__op`` filters as SQL lists, so a
virtual DocType's list view filters like any other.
"""

import math
import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from grunt.db.filters import as_list, is_truthy, split_key
from grunt.document.base import DocumentList
from grunt.search.terms import matches_text

# The same contract as the SQL side (tests/contract): values compared in one
# type, NULL never matching a comparison, LIKE patterns with % and _, text in
# case ignored, empty values last.


def _empty(raw: Any) -> bool:
    return raw in (None, "")


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _pair(raw: Any, val: Any) -> tuple[Any, Any] | None:
    """*raw* and *val* in one comparable type; ``None`` when *raw* is NULL (SQL:
    a comparison with NULL is never true) or they can't be compared."""
    if raw is None:
        return None
    if isinstance(raw, bool):  # before int: a bool is an int
        return raw, is_truthy(val)
    if isinstance(raw, (int, float, Decimal)):
        try:
            return float(raw), float(val)
        except TypeError, ValueError:
            return None
    if isinstance(raw, (date, datetime)) or isinstance(val, (date, datetime)):
        return str(_iso(raw)), str(_iso(val))
    return str(raw), str(val)


def _compare(test: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
    def match(raw: Any, val: Any) -> bool:
        pair = _pair(raw, val)
        return pair is not None and test(*pair)

    return match


def _like(raw: Any, val: Any) -> bool:
    """SQL ``ILIKE '%val%'``: ``%`` and ``_`` are wildcards, case ignored."""
    if raw is None:
        return False
    pattern = "".join(".*" if ch == "%" else "." if ch == "_" else re.escape(ch) for ch in str(val))
    return re.search(pattern, str(_iso(raw)), re.IGNORECASE | re.DOTALL) is not None


def _in(raw: Any, val: Any) -> bool:
    return any((p := _pair(raw, v)) is not None and p[0] == p[1] for v in as_list(val))


def _year(raw: Any, val: Any) -> bool:
    return not _empty(raw) and str(_iso(raw))[:4] == f"{int(str(val).strip()):04d}"


_eq = _compare(lambda a, b: a == b)
_lte = _compare(lambda a, b: a <= b)

# In-memory counterparts of grunt.db.filters._CLAUSES.
_ROW_MATCHERS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": _eq,
    "ne": _compare(lambda a, b: a != b),
    "neq": _compare(lambda a, b: a != b),
    "gt": _compare(lambda a, b: a > b),
    "gte": _compare(lambda a, b: a >= b),
    "lt": _compare(lambda a, b: a < b),
    "lte": _lte,
    "lte_or_null": lambda raw, val: raw is None or _lte(raw, val),
    "like": _like,
    "ilike": _like,
    "nlike": lambda raw, val: raw is None or not _like(raw, val),
    "in": _in,
    "nin": lambda raw, val: raw is not None and not _in(raw, val),
    "isnull": lambda raw, val: (raw is None) == is_truthy(val),
    "is": lambda raw, val: _empty(raw) == (str(val).strip().lower() == "not set"),
    "year": _year,
}


def _matches(match: Callable[[Any, Any], bool], raw: Any, val: Any) -> bool:
    try:
        return match(raw, val)
    except TypeError, ValueError:
        return False


def apply_filters(rows: list[dict], filters: dict[str, Any]) -> list[dict]:
    """Filter rows in memory with the same ``field__op`` syntax as SQL lists.

    An operator the SQL side doesn't know (``dept__child_of``) raises
    instead of quietly matching the wrong rows.
    """
    for key, val in filters.items():
        field, op = split_key(key)
        if "__" in field:
            raise ValueError(f"Unsupported filter operator in {key!r}")
        match = _ROW_MATCHERS.get(op)
        if match is None:
            raise NotImplementedError(f"Filter operator {op!r} not supported")
        rows = [r for r in rows if _matches(match, r.get(field), val)]
    return rows


def _sort_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()  # as SQL lower() - case ignored, then code points
    return _iso(value)


def apply_sort(rows: list[dict], sort_by: str, sort_order: str) -> list[dict]:
    """Sort *rows* like the SQL list: text case ignored, NULLs last either way,
    ``name`` breaking ties."""
    reverse = sort_order.lower() == "desc"
    present = [r for r in rows if r.get(sort_by) is not None]
    empty = [r for r in rows if r.get(sort_by) is None]

    def key(r: dict) -> tuple[Any, str]:
        return _sort_value(r.get(sort_by)), str(r.get("name", ""))

    try:
        present.sort(key=key, reverse=reverse)
    except TypeError:  # mixed types - compare as text
        present.sort(
            key=lambda r: (str(_iso(r.get(sort_by))), str(r.get("name", ""))), reverse=reverse
        )
    empty.sort(key=lambda r: str(r.get("name", "")), reverse=reverse)
    return present + empty


def apply_search(rows: list[dict], search: str, fields: list[str]) -> list[dict]:
    """Keep rows where every term of *search* appears (case-insensitive) in
    one of *fields* - the same semantics as the SQL list search."""
    return [r for r in rows if matches_text(search, (r.get(f) for f in fields))]


def build_response(
    rows: list[dict],
    page: int,
    per_page: int,
    *,
    extra_meta: dict[str, Any] | None = None,
) -> DocumentList:
    """Paginate *rows* and wrap in the standard Grunt list response.

    ``extra_meta`` is merged into ``meta`` as-is - e.g. a virtual DocType
    backed by a live external source (Redis, an API) can flag
    ``{"unavailable": True, "unavailable_message": "Redis не налаштований"}``
    when an empty list means "source unreachable" rather than "nothing
    there". The message is caller-supplied, ready-to-display text - the
    generic list UI never needs to know *why* a source is unavailable,
    only that it is.
    """
    total = len(rows)
    offset = (page - 1) * per_page
    page_rows = rows[offset : offset + per_page]
    meta: dict[str, Any] = {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if per_page else 1,
    }
    if extra_meta:
        meta.update(extra_meta)
    return DocumentList(data=page_rows, meta=meta)
