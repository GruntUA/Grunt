"""Virtual DocType adapter - base class for DocTypes backed by external data sources.

A Virtual DocType has `is_virtual=True` and does NOT create a database table.
Instead, the developer implements a controller class that inherits from
`VirtualDocType` and overrides the CRUD methods.

Usage:
    # In controllers/external_customer.py
    class ExternalCustomer(VirtualDocType):
        async def get_list(self, filters, page, per_page, **kwargs):
            return await my_external_api.list_customers(...)

        async def get(self, doc_id):
            return await my_external_api.get_customer(doc_id)

        async def create(self, data):
            return await my_external_api.create_customer(data)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from grunt.db.filters import as_list, is_truthy, split_key

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


class VirtualDocType:
    """Base class for Virtual DocType controllers.

    Override the CRUD methods to provide data from any external source
    (REST API, gRPC, 1С, GraphQL, file system, etc.).

    All methods receive the raw request data and should return dicts
    matching the DocType field structure.
    """

    # True when the DocType still has a table of its own that mirrors the
    # documents: list, count and date stats then query it like any regular
    # DocType, and only single-document reads and writes go through here.
    lists_from_table: bool = False

    def __init__(self, doctype: str, user: Any = None) -> None:
        self.doctype = doctype
        self.user = user

    async def get_list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "name",
        sort_order: str = "desc",
        search: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return a paginated list of documents.

        Must return: {"data": [...], "meta": {"total": N, "page": N, "per_page": N}}
        """
        raise NotImplementedError(f"Virtual DocType '{self.doctype}' must implement get_list()")

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        """Return a single document by ID.

        Must return a dict matching the DocType fields.
        """
        raise NotImplementedError(f"Virtual DocType '{self.doctype}' must implement get()")

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Create a new document.

        Returns the created document dict.
        """
        raise NotImplementedError(f"Virtual DocType '{self.doctype}' must implement create()")

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Update an existing document.

        Returns the updated document dict.
        """
        raise NotImplementedError(f"Virtual DocType '{self.doctype}' must implement update()")

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        """Delete a document by ID."""
        raise NotImplementedError(f"Virtual DocType '{self.doctype}' must implement delete()")

    async def get_count(self, filters: dict[str, Any] | None = None, **kwargs: Any) -> int:
        """Return the total count of documents matching filters.

        Default implementation calls get_list and reads meta.total.
        Override for efficiency.
        """
        result = await self.get_list(filters=filters, page=1, per_page=1, **kwargs)
        return result.get("meta", {}).get("total", 0)

    # In-memory helpers
    # Useful for virtual DocTypes backed by in-memory data (ring buffers,
    # external API responses, etc.).  Subclasses may call these directly
    # instead of re-implementing filtering / sorting / pagination logic.

    def apply_filters(self, rows: list[dict], filters: dict[str, Any]) -> list[dict]:
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

    def apply_sort(self, rows: list[dict], sort_by: str, sort_order: str) -> list[dict]:
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

    def apply_search(self, rows: list[dict], search: str, fields: list[str]) -> list[dict]:
        """Keep rows where *search* appears (case-insensitive) in any of *fields*."""
        q = search.lower()
        return [r for r in rows if any(q in str(r.get(f) or "").lower() for f in fields)]

    def build_response(
        self,
        rows: list[dict],
        page: int,
        per_page: int,
        *,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        return {"data": page_rows, "meta": meta}
