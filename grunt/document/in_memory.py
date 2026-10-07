"""Lists of documents held in memory - for controllers whose source is not a
table (a ring buffer, an API response, Redis).

``apply_filters`` takes the same ``field__op`` filters as SQL lists, so a
virtual DocType's list view filters like any other.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from grunt.db.filters import as_list, is_truthy, split_key
from grunt.document.base import DocumentList

if TYPE_CHECKING:
    from collections.abc import Callable


def _contains(raw: Any, val: Any) -> bool:
    return str(val).lower().strip("%") in str(raw).lower()


def _empty(raw: Any) -> bool:
    return raw in (None, "")


def _lte_or_null(raw: Any, val: Any) -> bool:
    if _empty(raw):
        return True
    try:
        return float(raw) <= float(val or 0)
    except TypeError, ValueError:
        return str(raw) <= str(val)


# In-memory counterparts of grunt.db.filters._CLAUSES.
_ROW_MATCHERS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda raw, val: str(raw) == str(val),
    "ne": lambda raw, val: str(raw) != str(val),
    "neq": lambda raw, val: str(raw) != str(val),
    "gt": lambda raw, val: float(raw or 0) > float(val or 0),
    "gte": lambda raw, val: float(raw or 0) >= float(val or 0),
    "lt": lambda raw, val: float(raw or 0) < float(val or 0),
    "lte": lambda raw, val: float(raw or 0) <= float(val or 0),
    "lte_or_null": _lte_or_null,
    "like": _contains,
    "ilike": _contains,
    "nlike": lambda raw, val: raw is None or not _contains(raw, val),
    "in": lambda raw, val: str(raw) in {str(v) for v in as_list(val)},
    "nin": lambda raw, val: str(raw) not in {str(v) for v in as_list(val)},
    "isnull": lambda raw, val: (raw is None) == is_truthy(val),
    "is": lambda raw, val: _empty(raw) == (str(val).strip().lower() == "not set"),
    "year": lambda raw, val: not _empty(raw) and str(raw)[:4] == f"{int(val):04d}",
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


def apply_sort(rows: list[dict], sort_by: str, sort_order: str) -> list[dict]:
    """Sort *rows* by *sort_by* field.  Nones are always placed last."""
    reverse = sort_order.lower() == "desc"
    try:
        return sorted(
            rows,
            key=lambda r: (r.get(sort_by) is None, r.get(sort_by) or 0),
            reverse=reverse,
        )
    except TypeError:
        return sorted(
            rows,
            key=lambda r: str(r.get(sort_by) or ""),
            reverse=reverse,
        )


def apply_search(rows: list[dict], search: str, fields: list[str]) -> list[dict]:
    """Keep rows where *search* appears (case-insensitive) in any of *fields*."""
    q = search.lower()
    return [r for r in rows if any(q in str(r.get(f) or "").lower() for f in fields)]


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
