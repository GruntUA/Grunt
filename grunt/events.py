"""Document event bus — the fan-out pipeline behind ``fire()``.

Every write in the CRUD pipeline
(:class:`grunt.document.mixins.write.DocumentWriteMixin`) ends in a single
``fire("after_save", ...)`` call. :func:`fire`:

1. Runs the hook registry via :func:`grunt.hooks.dispatch` — app ``@on`` /
   ``on_doc`` / ``doc_events`` handlers.
2. Walks :data:`SUBSCRIBERS` in ascending ``priority`` order — the framework's
   own side-effect subsystems (Server Scripts, backlink sync, notification
   rules, assignment rules) plus anything an app registered through
   :func:`subscribe`.

Each subscriber is best-effort: its exception is logged and the remaining
subscribers still run. The whole bus no-ops during bootstrap (fixture /
migration loading) so those never trigger notifications or server scripts.

Adding a stage means appending an :class:`EventSubscriber` — never editing
:func:`fire`.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from grunt.context import _bootstrap_ctx
from grunt.hooks import dispatch as _dispatch_hooks
from grunt.log import log

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable


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


# ─────────────────────────────────────────────────────────────────────────────
# Core pipeline stages
#
# These are framework-internal (not pluggable), but they are registered the
# same way an app's would be — as data in SUBSCRIBERS — so the dispatch loop
# in fire() stays a plain iteration. Each keeps its own lazy imports to avoid
# import cycles at module load.
# ─────────────────────────────────────────────────────────────────────────────

_SERVER_SCRIPT_EVENTS = frozenset(
    {
        "before_insert",
        "after_insert",
        "before_save",
        "after_save",
        "before_delete",
        "after_delete",
        "validate",
        "on_transition",
    }
)

_LINK_EVENTS = frozenset({"after_save", "after_insert", "after_delete"})

_ASSIGNMENT_EVENTS = frozenset({"after_save", "after_insert"})

_NOTIFICATION_EVENTS = frozenset({"after_insert", "after_save", "after_update", "on_transition"})

# DocTypes whose writes never warrant notification-rule evaluation: append-only
# logs, plus ``Notification`` itself (the fan-out table — evaluating rules on a
# Notification write would recursively enqueue more work).
_NOTIFICATION_EXCLUDED_DOCTYPES = frozenset(
    {"BackgroundTaskLog", "ErrorLog", "ActivityLog", "ViewLog", "Notification"}
)


def _user_email(kwargs: dict) -> str:
    user_obj = kwargs.get("user")
    return getattr(user_obj, "email", str(user_obj)) if user_obj else ""


async def _run_server_scripts(**kwargs: Any) -> None:
    """Server Scripts of type "DocType Event"."""
    doctype = kwargs.get("doctype")
    if not doctype or not kwargs.get("session"):
        return

    from grunt.scripting import server_script_runner

    await server_script_runner.run_doctype_event(
        session=kwargs["session"],
        doctype=doctype,
        event=kwargs["event"],
        doc=kwargs.get("doc", {}),
        user_email=_user_email(kwargs),
    )


async def _sync_document_links(**kwargs: Any) -> None:
    """Backlink sync on write, backlink cleanup on delete."""
    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc")
    session = kwargs.get("session")
    if not doctype or not doc or not session:
        return

    from grunt.document.links import link_service

    doc_id = str(doc.get("name", ""))
    if kwargs["event"] == "after_delete":
        await link_service.delete_links(session, doctype, doc_id)
    else:
        await link_service.sync_links(session, doctype, doc_id, doc)


async def _evaluate_notification_rules(**kwargs: Any) -> None:
    """Offload notification-rule evaluation to a background worker."""
    doctype = kwargs.get("doctype")
    event = kwargs["event"]
    if (
        not doctype
        or doctype in _NOTIFICATION_EXCLUDED_DOCTYPES
        or not kwargs.get("doc")
        or not kwargs.get("session")
    ):
        return

    from grunt.notification import rule_index

    # Skip the worker hop entirely unless a rule could actually match —
    # otherwise every document write queues a task and a log row.
    if not await rule_index.has_rules(doctype, event):
        return

    from grunt.notification.tasks import evaluate_notification_rules_task

    await evaluate_notification_rules_task.kiq(
        event=event,
        doctype=doctype,
        doc=kwargs["doc"],
        user_email=_user_email(kwargs),
    )


async def _evaluate_assignment_rules(**kwargs: Any) -> None:
    doctype = kwargs.get("doctype")
    if not doctype or not kwargs.get("doc") or not kwargs.get("session"):
        return

    from grunt.assignment import assignment_service

    await assignment_service.evaluate_and_assign(doctype=doctype, doc=kwargs["doc"])


for _core_stage in (
    EventSubscriber("server_scripts", _run_server_scripts, _SERVER_SCRIPT_EVENTS, priority=30),
    EventSubscriber("document_links", _sync_document_links, _LINK_EVENTS, priority=40),
    EventSubscriber(
        "notification_rules", _evaluate_notification_rules, _NOTIFICATION_EVENTS, priority=50
    ),
    EventSubscriber(
        "assignment_rules", _evaluate_assignment_rules, _ASSIGNMENT_EVENTS, priority=60
    ),
):
    register_subscriber(_core_stage)
