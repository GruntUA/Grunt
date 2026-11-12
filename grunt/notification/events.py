"""Code events - notifications the framework or an app raises from code.

Code doesn't compose and send a notification itself; it *triggers an event*::

    await trigger(
        "grunt.todo.assigned",
        doc=todo, doctype="ToDo",
        link=("Task", "T-1"),             # what the notification opens
        recipients=[assignee],            # "Event recipients" in the rule
        extra={"target": "Task T-1"},     # more template variables
    )

and every enabled ``Notification`` rule with ``event = "code"`` and this
``event_key`` decides who is told, what and through which channels. Each event
ships a *standard* rule with the text that used to live in the code - an
administrator can switch it off, reword it, add channels or recipients. No
enabled rule - nothing is sent.

Events are registered here (the core's) and by apps in ``hooks.py``::

    notification_events = [
        {"key": "my_app.order.paid", "label": "Order paid", "doctype": "Order"},
    ]

``extra`` values may be callables: they run in each recipient's language
(text the code composes - "Changed: Status, Amount").
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.db.api import GruntDB
from grunt.i18n import N_, _
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.metadata.dynamic_options import register_option_provider
from grunt.notification import rules

_db = GruntDB()  # stateless: reads through the context's session


@dataclass(frozen=True, slots=True)
class CodeEvent:
    """An event code may trigger; ``variables`` - what its ``extra`` carries
    (shown to whoever writes the rule's templates)."""

    key: str
    label: str
    doctype: str | None = None
    description: str = ""
    variables: tuple[str, ...] = field(default_factory=tuple)


_events: dict[str, CodeEvent] = {}


def register_event(
    key: str,
    label: str,
    *,
    doctype: str | None = None,
    description: str = "",
    variables: Iterable[str] = (),
) -> CodeEvent:
    event = CodeEvent(key, label, doctype, description, tuple(variables))
    _events[key] = event
    return event


def get_event(key: str) -> CodeEvent | None:
    return _events.get(key)


def list_events() -> list[CodeEvent]:
    return list(_events.values())


#: ``options_source`` of ``Notification.event_key``.
OPTIONS_SOURCE = "grunt.notification.event"
register_option_provider(OPTIONS_SOURCE, lambda: [(e.key, _(e.label)) for e in list_events()])


async def trigger(
    key: str,
    *,
    doc: dict[str, Any] | None = None,
    doctype: str | None = None,
    link: tuple[str, str] | None = None,
    recipients: Iterable[str] = (),
    actor: str = "",
    extra: dict[str, Any | Callable[[], Any]] | None = None,
    session: AsyncSession | None = None,
) -> int:
    """Run the enabled rules of code event *key*; returns how many recipients
    were notified. Never raises - a notification must not break the action
    that caused it."""
    session = session or require_session()
    if key not in _events:
        log.warning("notification.unknown_event", event_key=key)
    try:
        async with system_context(session):
            found = await _db.get_all(
                "Notification",
                filters={"event": "code", "event_key": key, "is_enabled": True},
                limit=100,
            )
        source = doctype or (_events[key].doctype if key in _events else None) or ""
        count = 0
        for rule in found:
            if rule.get("ref_doctype") and rule["ref_doctype"] != source:
                continue
            count += await rules.run(
                session,
                rule,
                source,
                dict(doc or {}),
                actor=actor,
                event=key,
                extra=extra,
                event_recipients=list(recipients),
                link=link,
            )
        return count
    except Exception:
        log.exception("notification.trigger_failed", event_key=key)
        return 0


# The core's events. Labels are marked for translation; descriptions name the
# template variables each one adds.
for _key, _label, _doctype, _vars in (
    ("grunt.todo.assigned", N_("Task assigned"), "ToDo", ("target", "note")),
    ("grunt.todo.completed", N_("Task completed"), "ToDo", ("target", "task")),
    ("grunt.todo.due", N_("Tasks due (daily digest)"), "ToDo", ("count", "overdue", "tasks")),
    ("grunt.reminder", N_("Reminder"), "Reminder", ("title", "note")),
    ("grunt.follow.changed", N_("Followed document changed"), None, ("title", "label", "fields")),
    ("grunt.follow.commented", N_("Followed document commented"), None, ("title", "text")),
    ("grunt.comment.mentioned", N_("Mentioned in a comment"), "Comment", ("text",)),
    ("grunt.comment.replied", N_("Reply to a comment"), "Comment", ("text",)),
    (
        "grunt.auto_repeat.created",
        N_("Auto repeat created a document"),
        "AutoRepeat",
        ("label", "created"),
    ),
    ("grunt.auto_repeat.failed", N_("Auto repeat failed"), "AutoRepeat", ("error",)),
    ("grunt.storage.failing", N_("Cloud storage failing"), "StorageRemote", ("error",)),
):
    register_event(_key, _label, doctype=_doctype, variables=_vars)
