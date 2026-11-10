"""Virtual DocType controller - Hooks.

Exposes every registered event hook (global Python hooks, DocType Python hooks
and database-backed Server Scripts) as a standard read-only Grunt DocType so it
can be browsed through the normal ListView instead of a bespoke admin page.

Read-only: list + load. Insert/update/delete are not supported.
"""

from typing import Any

from grunt import hooks
from grunt.document.base import Document
from grunt.i18n import N_
from grunt.query.query import Query
from grunt.store import VirtualStore
lazy from grunt.document.api import documents


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
        scripts = await documents.get_list(
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


class HookStore(VirtualStore):
    not_supported_message = N_("Hooks are read-only: they come from the code and Server Scripts")

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        return [_with_name(r) for r in _collect() + await _collect_server_scripts()]


class Hook(Document):
    store_class = HookStore
