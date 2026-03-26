"""Hook registry — event-driven extensibility for Grunt apps.

Usage in app hooks.py:

    from grunt.core.hooks import on, on_doc

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

import asyncio
import importlib
from collections import defaultdict
from typing import Any, Callable, Union, TypedDict

import structlog

logger = structlog.get_logger()

class HookDefinition(TypedDict):
    handler: Callable[..., Any]
    priority: int

# Global event hooks: event -> [HookDefinition]
HOOK_REGISTRY: dict[str, list[HookDefinition]] = defaultdict(list)

# DocType specific hooks: doctype -> event -> [HookDefinition]
DOC_EVENT_REGISTRY: dict[str, dict[str, list[HookDefinition]]] = defaultdict(
    lambda: defaultdict(list)
)


def on(event: str, priority: int = 10) -> Callable:
    """Decorator to register a global hook for an event."""

    def decorator(fn: Callable) -> Callable:
        HOOK_REGISTRY[event].append({"handler": fn, "priority": priority})
        HOOK_REGISTRY[event].sort(key=lambda x: x["priority"])
        logger.debug("hook.registered", event=event, fn=fn.__qualname__, priority=priority)
        return fn

    return decorator


def on_doc(doctype: str, event: str, priority: int = 10) -> Callable:
    """Decorator to register a DocType-specific hook."""

    def decorator(fn: Callable) -> Callable:
        DOC_EVENT_REGISTRY[doctype][event].append({"handler": fn, "priority": priority})
        DOC_EVENT_REGISTRY[doctype][event].sort(key=lambda x: x["priority"])
        logger.debug(
            "hook.doc_registered",
            doctype=doctype,
            event=event,
            fn=fn.__qualname__,
            priority=priority,
        )
        return fn

    return decorator


async def fire(event: str, **kwargs: Any) -> None:
    """Fire all registered hooks for an event.

    If `doctype` is present in kwargs, it also fires DocType-specific hooks.
    """
    # 1. Fire global hooks
    for hook in HOOK_REGISTRY.get(event, []):
        await _call_hook(hook["handler"], event, **kwargs)

    # 2. Fire DocType-specific hooks
    doctype = kwargs.get("doctype")
    if doctype and doctype in DOC_EVENT_REGISTRY:
        for hook in DOC_EVENT_REGISTRY[doctype].get(event, []):
            await _call_hook(hook["handler"], f"{doctype}:{event}", **kwargs)


async def _call_hook(fn: Callable, event_name: str, **kwargs: Any) -> None:
    try:
        if asyncio.iscoroutinefunction(fn):
            await fn(**kwargs)
        else:
            fn(**kwargs)
    except Exception:
        logger.exception(
            "hook.error", event=event_name, fn=getattr(fn, "__qualname__", str(fn))
        )


def register_doc_events(events: dict[str, dict[str, Union[str, list[Union[str, dict]]]]]) -> None:
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
                    module_path, func_name = path.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    fn = getattr(module, func_name)
                    DOC_EVENT_REGISTRY[doctype][event].append({"handler": fn, "priority": priority})
                    DOC_EVENT_REGISTRY[doctype][event].sort(key=lambda x: x["priority"])
                except (ImportError, AttributeError, ValueError) as e:
                    logger.warning(
                        "hook.register_failed",
                        path=path,
                        doctype=doctype,
                        event=event,
                        error=str(e),
                    )


def clear() -> None:
    """Clear all registered hooks (useful for tests)."""
    HOOK_REGISTRY.clear()
    DOC_EVENT_REGISTRY.clear()
