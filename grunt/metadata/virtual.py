"""Virtual DocType adapter — base class for DocTypes backed by external data sources.

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

from typing import Any

from grunt.db.filters import as_list, split_key


class VirtualDocType:
    """Base class for Virtual DocType controllers.

    Override the CRUD methods to provide data from any external source
    (REST API, gRPC, 1С, GraphQL, file system, etc.).

    All methods receive the raw request data and should return dicts
    matching the DocType field structure.
    """

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

    # ── In-memory helpers ─────────────────────────────────────────────────
    # Useful for virtual DocTypes backed by in-memory data (ring buffers,
    # external API responses, etc.).  Subclasses may call these directly
    # instead of re-implementing filtering / sorting / pagination logic.

    def apply_filters(self, rows: list[dict], filters: dict[str, Any]) -> list[dict]:
        """Filter *rows* using the standard Grunt filter syntax.

        Supported operators (appended to fieldname with ``__``):
            eq (default), ne, neq, gt, gte, lt, lte, lte_or_null, like, ilike,
            nlike, in, nin, isnull, is (``set`` / ``not set``), year

        Keys are parsed by ``grunt.db.filters.split_key``, the same as the
        SQL-backed ``build_clauses``. An unknown operator (``status__typo``,
        ``dept__child_of``) or one in ``FILTER_OPS`` not implemented below
        raises rather than silently returning the wrong rows.
        """
        for key, val in filters.items():
            field, op = split_key(key)
            if "__" in field:
                raise ValueError(f"Unsupported filter operator in {key!r}")

            result: list[dict] = []
            for r in rows:
                raw = r.get(field)
                try:
                    if op == "eq":
                        match = str(raw) == str(val)
                    elif op in ("ne", "neq"):
                        match = str(raw) != str(val)
                    elif op in ("like", "ilike"):
                        match = str(val).lower().strip("%") in str(raw).lower()
                    elif op == "nlike":
                        match = raw is None or str(val).lower().strip("%") not in str(raw).lower()
                    elif op == "is":
                        empty = raw in (None, "")
                        match = empty if str(val).strip().lower() == "not set" else not empty
                    elif op in ("gt", "gte", "lt", "lte"):
                        a, b = float(raw or 0), float(val or 0)
                        match = (
                            a > b
                            if op == "gt"
                            else a >= b
                            if op == "gte"
                            else a < b
                            if op == "lt"
                            else a <= b
                        )
                    elif op == "lte_or_null":
                        if raw in (None, ""):
                            match = True
                        else:
                            try:
                                match = float(raw) <= float(val or 0)
                            except TypeError, ValueError:
                                match = str(raw) <= str(val)
                    elif op == "in":
                        match = str(raw) in [str(v) for v in as_list(val)]
                    elif op == "nin":
                        match = str(raw) not in [str(v) for v in as_list(val)]
                    elif op == "year":
                        match = raw not in (None, "") and str(raw)[:4] == f"{int(val):04d}"
                    elif op == "isnull":
                        match = (
                            (raw is None)
                            if str(val).lower() in ("true", "1")
                            else (raw is not None)
                        )
                    else:  # in FILTER_OPS but not handled here — not swallowed below
                        raise NotImplementedError(f"Filter operator {op!r} not supported")
                except TypeError, ValueError:
                    match = False
                if match:
                    result.append(r)
            rows = result
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

        ``extra_meta`` is merged into ``meta`` as-is — e.g. a virtual DocType
        backed by a live external source (Redis, an API) can flag
        ``{"unavailable": True, "unavailable_message": "Redis не налаштований"}``
        when an empty list means "source unreachable" rather than "nothing
        there". The message is caller-supplied, ready-to-display text — the
        generic list UI never needs to know *why* a source is unavailable,
        only that it is.
        """
        import math

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
