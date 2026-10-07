"""Virtual DocType controller - Hooks.

Exposes every registered event hook (global Python hooks, DocType Python hooks
and database-backed Server Scripts) as a standard read-only Grunt DocType so it
can be browsed through the normal ListView instead of a bespoke admin page.

Read-only: list + load. Insert/update/delete are not supported.
"""

from __future__ import annotations

from typing import Any

import grunt
from grunt import _, hooks
from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import apply_filters, apply_search, apply_sort, build_response
from grunt.errors import not_found

_SEARCH_FIELDS = ["event", "handler", "reference_doctype", "source"]


def _handler_name(handler: Any) -> str:
    """Best-effort stable, readable name for a Python hook target."""
    mod = getattr(handler, "__module__", None)
    qual = getattr(handler, "__qualname__", None) or getattr(handler, "__name__", None)
    if mod and qual:
        return f"{mod}.{qual}"
    return str(handler)


def _collect() -> list[dict[str, Any]]:
    """Gather every Python hook (global + DocType) into row dicts."""
    rows: list[dict[str, Any]] = []

    for event, entries in hooks.HOOK_REGISTRY.items():
        for h in entries:
            rows.append(
                {
                    "source": "Python (Global)",
                    "event": event,
                    "handler": _handler_name(h["handler"]),
                    "priority": h["priority"],
                    "reference_doctype": "*",
                }
            )

    for doctype, events in hooks.DOC_EVENT_REGISTRY.items():
        for event, entries in events.items():
            for h in entries:
                rows.append(
                    {
                        "source": "Python (DocType)",
                        "event": event,
                        "handler": _handler_name(h["handler"]),
                        "priority": h["priority"],
                        "reference_doctype": doctype,
                    }
                )

    return rows


async def _collect_server_scripts() -> list[dict[str, Any]]:
    """Gather enabled Server Scripts registered as event/API hooks."""
    rows: list[dict[str, Any]] = []
    try:
        scripts = await grunt.get_list(
            "ServerScript",
            filters={"disabled": False},
            fields=["event", "script_type", "api_method", "name", "reference_doctype"],
            limit=1000,
        )
    except Exception:
        from grunt import log

        log.exception("hook.server_scripts_failed")
        return rows

    for s in scripts:
        is_doc_event = s["script_type"] == "DocType Event"
        rows.append(
            {
                "source": "Database (Server Script)",
                "event": s["event"] if is_doc_event else (s.get("api_method") or "Global"),
                "handler": s["name"],
                "priority": 10,
                "reference_doctype": s.get("reference_doctype") if is_doc_event else "*",
            }
        )
    return rows


def _with_name(row: dict[str, Any]) -> dict[str, Any]:
    name = f"{row['reference_doctype']}::{row['event']}::{row['handler']}"
    return {"id": name, "name": name, **row}


class Hook(BaseDocument):
    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "reference_doctype",
        sort_order: str = "asc",
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        **kwargs: Any,
    ) -> DocumentList:
        rows = _collect() + await _collect_server_scripts()

        if search:
            rows = apply_search(rows, search, _SEARCH_FIELDS)
        if filters:
            rows = apply_filters(rows, filters)
        # A list view sorts by modified_at by default - hooks have no such field.
        if not sort_by or sort_by == "modified_at":
            sort_by = "reference_doctype"
        rows = apply_sort(rows, sort_by, sort_order)

        response = build_response(rows, page, per_page)
        return DocumentList([_with_name(r) for r in response], response.meta)

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        rows = _collect() + await _collect_server_scripts()
        for row in rows:
            named = _with_name(row)
            if named["name"] == self.name:
                self.data = named
                return
        raise not_found(_("Hook '%(doc_id)s' not found") % {"doc_id": self.name})
