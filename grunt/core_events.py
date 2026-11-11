"""The framework's own document-event stages, registered on the bus
(:mod:`grunt.events`) like an app's subscribers would be.

Framework-internal, not pluggable. :func:`grunt.events.fire` imports this
module by path before the first event - the bus itself knows none of the
subsystems below.
"""

from typing import Any

from grunt.assignment import assignment_service
from grunt.document.links import link_service
from grunt.events import EventSubscriber, register_subscriber
from grunt.i18n import _
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.notification import rule_index
from grunt.notification.service import notification_service
from grunt.notification.tasks import evaluate_notification_rules_task
from grunt.scripting import server_script_runner
from grunt.storage.cloud import REMOTE_FAILED
from grunt.storage.references import claim_referenced_files
from grunt.tasks.enqueue import enqueue

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

_FILE_CLAIM_EVENTS = frozenset({"after_save"})

_NOTIFICATION_EVENTS = frozenset({"after_insert", "after_save", "after_update", "on_transition"})


def _user_email(kwargs: dict) -> str:
    user_obj = kwargs.get("user")
    return getattr(user_obj, "email", str(user_obj)) if user_obj else ""


async def _run_server_scripts(**kwargs: Any) -> None:
    """Server Scripts of type "DocType Event"."""
    doctype = kwargs.get("doctype")
    if not doctype or not kwargs.get("session"):
        return

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

    doc_id = str(doc.get("name", ""))
    if kwargs["event"] == "after_delete":
        await link_service.delete_links(session, doctype, doc_id)
    else:
        await link_service.sync_links(session, doctype, doc_id, doc)


async def _claim_referenced_files(**kwargs: Any) -> None:
    """Bind pending uploads the saved document points at (grunt.storage.references)."""
    if not kwargs.get("session"):
        return

    await claim_referenced_files(**kwargs)


async def _evaluate_notification_rules(**kwargs: Any) -> None:
    """Offload notification-rule evaluation to a background worker."""
    doctype = kwargs.get("doctype")
    event = kwargs["event"]
    if not doctype or not kwargs.get("doc") or not kwargs.get("session"):
        return
    # ``Notification`` is the fan-out sink itself - evaluating rules on its own
    # writes would recursively enqueue more work. Append-only system logs
    # (``DocType.is_log``) never warrant notification rules either.
    if doctype == "Notification":
        return

    try:
        dt = await doctype_registry.get(doctype)
    except Exception:
        dt = None
    if dt is not None and getattr(dt, "is_log", False):
        return

    # Skip the worker hop entirely unless a rule could actually match -
    # otherwise every document write queues a task and a log row.
    if not await rule_index.has_rules(doctype, event):
        return

    # After the commit: the worker reads the document this transaction saved.
    enqueue(
        evaluate_notification_rules_task,
        event=event,
        doctype=doctype,
        doc=kwargs["doc"],
        user_email=_user_email(kwargs),
    )


async def _evaluate_assignment_rules(**kwargs: Any) -> None:
    doctype = kwargs.get("doctype")
    if not doctype or not kwargs.get("doc") or not kwargs.get("session"):
        return

    await assignment_service.evaluate_and_assign(doctype=doctype, doc=kwargs["doc"])


async def _alert_remote_failure(**kwargs: Any) -> None:
    """A cloud storage remote turned from OK to Error: tell the System Managers."""
    name = kwargs["doc_id"]
    session = kwargs["session"]
    try:
        users = await notification_service._resolve_role_recipients(["System Manager"], session)
        for user in users:
            await notification_service.notify(
                session,
                user=user,
                doctype="StorageRemote",
                doc_id=name,
                subject=_("Cloud storage “%(name)s” is failing") % {"name": name},
                message=kwargs["message"],
            )
    except Exception:
        log.warning("cloud.notify_failed", remote=name, exc_info=True)


for _core_stage in (
    EventSubscriber("server_scripts", _run_server_scripts, _SERVER_SCRIPT_EVENTS, priority=30),
    EventSubscriber("document_links", _sync_document_links, _LINK_EVENTS, priority=40),
    EventSubscriber("file_references", _claim_referenced_files, _FILE_CLAIM_EVENTS, priority=45),
    EventSubscriber(
        "notification_rules", _evaluate_notification_rules, _NOTIFICATION_EVENTS, priority=50
    ),
    EventSubscriber(
        "assignment_rules", _evaluate_assignment_rules, _ASSIGNMENT_EVENTS, priority=60
    ),
    EventSubscriber(
        "storage_remote_alert", _alert_remote_failure, frozenset({REMOTE_FAILED}), priority=70
    ),
):
    register_subscriber(_core_stage)
