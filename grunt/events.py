"""Document event bus - the fan-out pipeline behind ``fire()``.

Every write in the CRUD pipeline
(:mod:`grunt.document.mixins.lifecycle`) ends in a single
``fire("after_save", ...)`` call. :func:`fire`:

1. Runs the hook registry via :func:`grunt.hooks.dispatch` - app ``@on`` /
   ``on_doc`` / ``doc_events`` handlers.
2. Walks :data:`SUBSCRIBERS` in ascending ``priority`` order - the framework's
   own side-effect subsystems (Server Scripts, backlink sync, pending-upload
   claiming, notification rules, assignment rules) plus anything an app registered through
   :func:`subscribe`.

Each subscriber is best-effort: its exception is logged and the remaining
subscribers still run. The whole bus no-ops during bootstrap (fixture /
migration loading) so those never trigger notifications or server scripts.

Adding a stage means appending an :class:`EventSubscriber` - never editing
:func:`fire`.
"""

import importlib
import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from grunt.hooks import dispatch as _dispatch_hooks
from grunt.local import _bootstrap_ctx
from grunt.log import log


@dataclass(frozen=True, slots=True)
class EventSubscriber:
    """One stage of the event pipeline.

    ``events`` limits the stage to a set of lifecycle events; ``None`` means
    every event. Lower ``priority`` runs first.
    """

    name: str
    handler: Callable[..., Awaitable[Any] | Any]
    events: frozenset[str] | None = None
    priority: int = 50

    def matches(self, event: str) -> bool:
        return self.events is None or event in self.events


SUBSCRIBERS: list[EventSubscriber] = []

# The framework's own stages (server scripts, backlinks, file claims,
# notification and assignment rules) - a module above the document layer that
# registers them. Imported by path before the first event, so the bus never
# imports the subsystems and a stage can't be missed because nothing imported it.
_CORE_STAGES = "grunt.core_events"
_core_loaded = False


def _load_core_stages() -> None:
    global _core_loaded
    if not _core_loaded:
        importlib.import_module(_CORE_STAGES)
        _core_loaded = True


def register_subscriber(sub: EventSubscriber) -> None:
    """Add (or replace, by name) a subscriber and keep the list priority-sorted."""
    SUBSCRIBERS[:] = sorted(
        [s for s in SUBSCRIBERS if s.name != sub.name] + [sub],
        key=lambda s: s.priority,
    )
    log.debug("event.subscriber_registered", subscriber=sub.name, priority=sub.priority)


def unsubscribe(name: str) -> None:
    """Remove a subscriber by name (no-op if absent). Mainly for tests."""
    SUBSCRIBERS[:] = [s for s in SUBSCRIBERS if s.name != name]


def subscribe(
    name: str,
    *,
    events: Iterable[str] | None = None,
    priority: int = 50,
) -> Callable:
    """Decorator form of :func:`register_subscriber`.

    @subscribe("audit_export", events={"after_insert", "after_delete"})
    async def _push(doctype, doc, **kwargs): ...
    """

    def decorator(fn: Callable) -> Callable:
        register_subscriber(
            EventSubscriber(
                name=name,
                handler=fn,
                events=frozenset(events) if events is not None else None,
                priority=priority,
            )
        )
        return fn

    return decorator


async def fire(event: str, **kwargs: Any) -> None:
    """Fire a document lifecycle event through the whole pipeline.

    No-ops entirely during bootstrap (``_bootstrap_ctx``). Runs the hook
    registry first, then every matching subscriber in priority order.
    """
    if _bootstrap_ctx.get():
        log.debug("event.skipped", reason="bootstrap", hook_event=event)
        return
    _load_core_stages()

    kwargs["event"] = event

    await _dispatch_hooks(**kwargs)

    for sub in SUBSCRIBERS:
        if not sub.matches(event):
            continue
        try:
            result = sub.handler(**kwargs)
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception("event.subscriber_error", subscriber=sub.name, hook_event=event)
