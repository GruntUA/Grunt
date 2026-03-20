"""Hook registry — event-driven extensibility for Grunt apps.

Usage in app hooks.py:

    from grunt.core.hooks import on

    @on("after_save")
    async def my_hook(doctype, doc, user, **kwargs):
        ...

Events fired by core:
    before_save   (doctype, doc, user, session)
    after_save    (doctype, doc, user, session)
    before_delete (doctype, doc, user, session)
    after_delete  (doctype, doc_id, user, session)
    on_transition (doctype, doc, from_state, to_state, action, user, session)
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable

import structlog

logger = structlog.get_logger()

HOOK_REGISTRY: dict[str, list[Callable[..., Any]]] = defaultdict(list)


def on(event: str) -> Callable:
    """Decorator to register a hook for an event."""

    def decorator(fn: Callable) -> Callable:
        HOOK_REGISTRY[event].append(fn)
        logger.debug("hook.registered", event=event, fn=fn.__qualname__)
        return fn

    return decorator


async def fire(event: str, **kwargs: Any) -> None:
    """Fire all registered hooks for an event."""
    for fn in HOOK_REGISTRY.get(event, []):
        try:
            if asyncio.iscoroutinefunction(fn):
                await fn(**kwargs)
            else:
                fn(**kwargs)
        except Exception:
            logger.exception(
                "hook.error", event=event, fn=fn.__qualname__
            )


def clear() -> None:
    """Clear all registered hooks (useful for tests)."""
    HOOK_REGISTRY.clear()
