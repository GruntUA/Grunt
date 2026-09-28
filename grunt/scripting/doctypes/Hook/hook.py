"""Virtual DocType controller — Hooks.

Exposes every registered event hook (global Python hooks, DocType Python hooks
and database-backed Server Scripts) as a standard read-only Grunt DocType so it
can be browsed through the normal ListView instead of a bespoke admin page.

Read-only: list + get. Create/update/delete are not supported.
"""

from __future__ import annotations

from typing import Any

from grunt.i18n import _
from grunt.metadata.virtual import VirtualDocType

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
    from grunt.hooks import DOC_EVENT_REGISTRY, HOOK_REGISTRY

    rows: list[dict[str, Any]] = []

    for event, entries in HOOK_REGISTRY.items():
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

    for doctype, events in DOC_EVENT_REGISTRY.items():
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
    import grunt

    rows: list[dict[str, Any]] = []
    try:
        scripts = await grunt.get_list(
            "ServerScript",
            filters={"disabled": False},
            fields=["event", "script_type", "api_method", "name", "reference_doctype"],
            limit=1000,
        )
    except Exception:
        from grunt.log import log

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


class Hook(VirtualDocType):
    async def get_list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "reference_doctype",
        sort_order: str = "asc",
        search: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        rows = _collect() + await _collect_server_scripts()

        if search:
            rows = self.apply_search(rows, search, _SEARCH_FIELDS)
        if filters:
            rows = self.apply_filters(rows, filters)
        rows = self.apply_sort(rows, sort_by or "reference_doctype", sort_order)

        response = self.build_response(rows, page, per_page)
        response["data"] = [_with_name(r) for r in response["data"]]
        return response

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        from fastapi import HTTPException, status

        rows = _collect() + await _collect_server_scripts()
        for row in rows:
            named = _with_name(row)
            if named["name"] == doc_id:
                return named
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Hook '%(doc_id)s' not found") % {"doc_id": doc_id},
        )

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Read-only")

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Read-only")

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Read-only")
