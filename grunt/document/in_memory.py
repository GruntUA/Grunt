"""Lists of documents held in memory - for controllers whose source is not a
table (a ring buffer, an API response, Redis).

``apply_filters`` takes the same ``field__op`` filters as SQL lists, so a
virtual DocType's list view filters like any other.
"""

import math
from typing import Any

from grunt.document.base import DocumentList
from grunt.query.evaluate import iso, matches
from grunt.query.parse import parse_filters
from grunt.search.terms import matches_text


def apply_filters(rows: list[dict], filters: dict[str, Any]) -> list[dict]:
    """Filter rows in memory with the same ``field__op`` syntax as SQL lists -
    the same query AST, evaluated by :mod:`grunt.query.evaluate`.

    An operator the SQL side doesn't know (``dept__child_of``) raises
    instead of quietly matching the wrong rows.
    """
    expr = parse_filters(filters)
    return [r for r in rows if matches(expr, r)]


def _sort_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()  # as SQL lower() - case ignored, then code points
    return iso(value)


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
            key=lambda r: (str(iso(r.get(sort_by))), str(r.get("name", ""))), reverse=reverse
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
