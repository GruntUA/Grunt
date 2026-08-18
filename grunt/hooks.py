"""Hook registry — event-driven extensibility for Grunt apps.

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

import structlog

from grunt.context import _bootstrap_ctx

if TYPE_CHECKING:
    from collections.abc import Callable

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

# DocType field extensions: doctype_name -> {"add_fields": [...]}
# Populated by apps via doctype_overrides in their hooks.py.
# Applied by startup.apply_doctype_overrides() after all DocTypes are loaded.
DOCTYPE_OVERRIDES: dict[str, dict] = {}


def on(event: str, priority: int = 10) -> Callable:
    """Decorator to register a global hook for an event."""

    def decorator(fn: Callable) -> Callable:
        HOOK_REGISTRY[event].append({"handler": fn, "priority": priority})
        HOOK_REGISTRY[event].sort(key=lambda x: x["priority"])
        logger.debug("hook.registered", event_name=event, fn=fn.__qualname__, priority=priority)
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
            event_name=event,
            fn=fn.__qualname__,
            priority=priority,
        )
        return fn

    return decorator


_NOTIFICATION_EVENTS = frozenset({"after_insert", "after_save", "after_update", "on_transition"})

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


async def fire(event: str, **kwargs: Any) -> None:
    """Fire an event through every side-effect subsystem the framework wires up.

    This is the shared bus behind the whole CRUD pipeline
    (:class:`~grunt.document.mixins.write.DocumentWriteMixin`) — a single
    ``fire("after_save", ...)`` call fans out to, in order:

    1. Global hooks registered via :func:`on`.
    2. DocType-specific hooks registered via :func:`on_doc` (wildcard ``"*"`` first).
    3. Server Scripts of type "DocType Event" (``before_insert``, ``after_insert``,
       ``before_save``, ``after_save``, ``before_delete``, ``after_delete``,
       ``validate``, ``on_transition`` only).
    4. Backlink sync/cleanup (``after_save``/``after_insert`` sync links,
       ``after_delete`` removes them).
    5. Notification rule evaluation, offloaded to a background worker
       (``after_insert``/``after_save``/``after_update``/``on_transition`` only,
       excluding log DocTypes).
    6. Assignment rule evaluation (``after_save``/``after_insert`` only).

    Each stage is independently best-effort: an exception in one subsystem is
    logged and does not stop the rest from running. No-ops entirely during
    bootstrap (``_bootstrap_ctx``) so fixture/migration loading never triggers
    notifications or server scripts.
    """
    if _bootstrap_ctx.get():
        logger.debug("hook.skipped", reason="bootstrap", hook_event=event)
        return

    kwargs["event"] = event

    # 1. Fire global hooks
    for hook in HOOK_REGISTRY.get(event, []):
        await _call_hook(hook["handler"], event, **kwargs)

    # 2. Fire DocType-specific hooks
    doctype = kwargs.get("doctype")
    if doctype:
        # Fire wildcard hooks first
        if "*" in DOC_EVENT_REGISTRY:
            for hook in DOC_EVENT_REGISTRY["*"].get(event, []):
                await _call_hook(hook["handler"], f"*:{event}", **kwargs)

        if doctype in DOC_EVENT_REGISTRY:
            for hook in DOC_EVENT_REGISTRY[doctype].get(event, []):
                await _call_hook(hook["handler"], f"{doctype}:{event}", **kwargs)

    # 3. Run Server Scripts (DocType Event type)
    if event in _SERVER_SCRIPT_EVENTS and doctype and kwargs.get("session"):
        try:
            from grunt.scripting import server_script_runner

            user_email = ""
            user_obj_ss = kwargs.get("user")
            if user_obj_ss:
                user_email = getattr(user_obj_ss, "email", str(user_obj_ss))

            await server_script_runner.run_doctype_event(
                session=kwargs["session"],
                doctype=doctype,
                event=event,
                doc=kwargs.get("doc", {}),
                user_email=user_email,
            )
        except Exception:
            logger.exception("server_script.hook_error", hook_event=event, doctype=doctype)

    # 4. Sync document links (backlinks)
    if (
        event in ("after_save", "after_insert")
        and doctype
        and kwargs.get("doc")
        and kwargs.get("session")
    ):
        try:
            from grunt.document.links import link_service

            doc = kwargs["doc"]
            doc_id = doc.get("name", "")
            await link_service.sync_links(kwargs["session"], doctype, str(doc_id), doc)
        except Exception:
            logger.exception("links.sync_error", hook_event=event, doctype=doctype)

    if event == "after_delete" and doctype and kwargs.get("doc") and kwargs.get("session"):
        try:
            from grunt.document.links import link_service

            doc = kwargs["doc"]
            doc_id = doc.get("name", "")
            await link_service.delete_links(kwargs["session"], doctype, str(doc_id))
        except Exception:
            logger.exception("links.delete_error", hook_event=event, doctype=doctype)

    # 5. Evaluate notification rules (Background)
    if (
        event in _NOTIFICATION_EVENTS
        and doctype
        and doctype not in {"BackgroundTaskLog", "ErrorLog", "ActivityLog"}
        and kwargs.get("doc")
        and kwargs.get("session")
    ):
        try:
            from grunt.notification.tasks import (
                evaluate_notification_rules_task,
            )

            user_email = ""
            user_obj = kwargs.get("user")
            if user_obj:
                user_email = getattr(user_obj, "email", str(user_obj))

            # Send to background worker
            await evaluate_notification_rules_task.kiq(
                event=event,
                doctype=doctype,
                doc=kwargs["doc"],
                user_email=user_email,
            )
        except Exception:
            logger.exception("notification.offload_error", hook_event=event, doctype=doctype)

    # 6. Evaluate assignment rules
    if (
        event in ("after_save", "after_insert")
        and doctype
        and kwargs.get("doc")
        and kwargs.get("session")
    ):
        try:
            from grunt.assignment import assignment_service

            await assignment_service.evaluate_and_assign(
                doctype=doctype,
                doc=kwargs["doc"],
            )
        except Exception:
            logger.exception("assignment.evaluate_error", hook_event=event, doctype=doctype)


async def _call_hook(fn: Callable, event_name: str, **kwargs: Any) -> None:
    try:
        if inspect.iscoroutinefunction(fn):
            await fn(**kwargs)
        else:
            fn(**kwargs)
    except Exception:
        logger.exception(
            "hook.error", hook_event=event_name, fn=getattr(fn, "__qualname__", str(fn))
        )


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
        logger.debug("hooks.doctype_overrides_registered", doctype=doctype_name)


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
                    logger.warning(
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
