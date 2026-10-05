"""Hook registry - event-driven extensibility for Grunt apps.

This module owns hook *registration* and *dispatch* only. The document event
bus that fans a lifecycle event out to framework subsystems (Server Scripts,
backlink sync, notification rules, assignment rules) lives in
:mod:`grunt.events`; its ``fire()`` calls :func:`dispatch` here first.

Usage in app hooks.py:

    from grunt.hooks import on, on_doc

    @on("after_save", priority=5)
    async def global_hook(doctype, doc, user, **kwargs):
        ...

    @on_doc("SalesOrder", "after_submit")
    async def specific_hook(doc, user, **kwargs):
        ...

    # Or define as a dictionary:
    doc_events = {
        "SalesOrder": {
            "after_save": [
                {"handler": "my_app.tasks.on_save", "priority": 1}
            ]
        }
    }
"""

from __future__ import annotations

import importlib
import inspect
from collections import defaultdict
from typing import TYPE_CHECKING, Any, TypedDict

from grunt import log

if TYPE_CHECKING:
    from collections.abc import Callable


class HookDefinition(TypedDict):
    handler: Callable[..., Any]
    priority: int


# Global event hooks: event -> [HookDefinition]
HOOK_REGISTRY: dict[str, list[HookDefinition]] = defaultdict(list)

# DocType specific hooks: doctype -> event -> [HookDefinition]
DOC_EVENT_REGISTRY: dict[str, dict[str, list[HookDefinition]]] = defaultdict(
    lambda: defaultdict(list)
)

# DocType field extensions: doctype_name -> {"add_fields": [...]}
# Populated by apps via doctype_overrides in their hooks.py.
# Applied by startup.apply_doctype_overrides() after all DocTypes are loaded.
DOCTYPE_OVERRIDES: dict[str, dict] = {}


def on(event: str, priority: int = 10) -> Callable:
    """Decorator to register a global hook for an event."""

    def decorator(fn: Callable) -> Callable:
        HOOK_REGISTRY[event].append({"handler": fn, "priority": priority})
        HOOK_REGISTRY[event].sort(key=lambda x: x["priority"])
        log.debug("hook.registered", event_name=event, fn=fn.__qualname__, priority=priority)
        return fn

    return decorator


def on_doc(doctype: str, event: str, priority: int = 10) -> Callable:
    """Decorator to register a DocType-specific hook."""

    def decorator(fn: Callable) -> Callable:
        DOC_EVENT_REGISTRY[doctype][event].append({"handler": fn, "priority": priority})
        DOC_EVENT_REGISTRY[doctype][event].sort(key=lambda x: x["priority"])
        log.debug(
            "hook.doc_registered",
            doctype=doctype,
            event_name=event,
            fn=fn.__qualname__,
            priority=priority,
        )
        return fn

    return decorator


async def dispatch(**kwargs: Any) -> None:
    """Run every registered hook for ``kwargs["event"]``.

    Global hooks (:func:`on`) first, then DocType-specific hooks
    (:func:`on_doc` / ``doc_events``) with the wildcard ``"*"`` DocType before
    the concrete one. This is the hook-registry half of the document event
    bus; the subsystem pipeline lives in :func:`grunt.events.fire`, which
    calls this first (``event`` is already present in ``kwargs``).

    Best-effort per handler: an exception is logged and the rest still run.
    """
    event = kwargs["event"]
    for hook in HOOK_REGISTRY.get(event, []):
        await _call_hook(hook["handler"], event, **kwargs)

    doctype = kwargs.get("doctype")
    if not doctype:
        return

    if "*" in DOC_EVENT_REGISTRY:
        for hook in DOC_EVENT_REGISTRY["*"].get(event, []):
            await _call_hook(hook["handler"], f"*:{event}", **kwargs)

    if doctype in DOC_EVENT_REGISTRY:
        for hook in DOC_EVENT_REGISTRY[doctype].get(event, []):
            await _call_hook(hook["handler"], f"{doctype}:{event}", **kwargs)


async def _call_hook(fn: Callable, event_name: str, **kwargs: Any) -> None:
    try:
        if inspect.iscoroutinefunction(fn):
            await fn(**kwargs)
        else:
            fn(**kwargs)
    except Exception:
        log.exception("hook.error", hook_event=event_name, fn=getattr(fn, "__qualname__", str(fn)))


def register_doctype_overrides(overrides: dict[str, dict]) -> None:
    """Register field extensions for existing DocTypes from an app's hooks.py.

    Format::

        doctype_overrides = {
            "User": {
                "add_fields": [
                    {"fieldname": "organization", "label": "Організація",
                     "fieldtype": "Link", "options": "Organization"}
                ]
            }
        }

    Applied by ``startup.apply_doctype_overrides()`` after all DocTypes are loaded.
    """
    for doctype_name, spec in overrides.items():
        if doctype_name not in DOCTYPE_OVERRIDES:
            DOCTYPE_OVERRIDES[doctype_name] = {"add_fields": []}
        existing_fieldnames = {
            f["fieldname"] for f in DOCTYPE_OVERRIDES[doctype_name].get("add_fields", [])
        }
        for field_def in spec.get("add_fields", []):
            if field_def.get("fieldname") not in existing_fieldnames:
                DOCTYPE_OVERRIDES[doctype_name].setdefault("add_fields", []).append(field_def)
        log.debug("hooks.doctype_overrides_registered", doctype=doctype_name)


def register_doc_events(events: dict[str, dict[str, str | list[str | dict]]]) -> None:
    """Register hooks from a dictionary (e.g. from app's hooks.py).

    Format:
    {
        "DocType": {
            "event": ["path.to.function", {"handler": "path", "priority": 1}]
        }
    }
    """
    for doctype, event_map in events.items():
        for event, handlers in event_map.items():
            if isinstance(handlers, (str, dict)):
                handlers = [handlers]

            for item in handlers:
                path = item if isinstance(item, str) else item.get("handler")
                priority = 10 if isinstance(item, str) else item.get("priority", 10)

                try:
                    if not path:
                        continue
                    module_path, func_name = path.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    fn = getattr(module, func_name)
                    DOC_EVENT_REGISTRY[doctype][event].append({"handler": fn, "priority": priority})
                    DOC_EVENT_REGISTRY[doctype][event].sort(key=lambda x: x["priority"])
                except (ImportError, AttributeError, ValueError) as e:
                    log.warning(
                        "hook.register_failed",
                        path=path,
                        doctype=doctype,
                        hook_event=event,
                        error=str(e),
                    )


def clear() -> None:
    """Clear all registered hooks (useful for tests)."""
    HOOK_REGISTRY.clear()
    DOC_EVENT_REGISTRY.clear()
    DOCTYPE_OVERRIDES.clear()
