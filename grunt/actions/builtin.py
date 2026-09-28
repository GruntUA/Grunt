"""Built-in document actions shipped with core.

Generic, DocType-agnostic (``doctypes=["*"]``) — they stay invisible until an
admin binds one from a DocType's **Actions** tab. Handy as ready-made buttons
and as worked examples of the ``@doc_action`` contract.

`run()` guarantees ``doc["doctype"]`` and ``doc["name"]`` are always set.
"""

from __future__ import annotations

from typing import Any

import grunt
from grunt.actions.registry import doc_action
from grunt.i18n import _


@doc_action(
    "core.duplicate",
    label="Duplicate",
    doctypes=["*"],
    icon="copy",
    variant="outline",
)
async def duplicate(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Create a fresh copy of the current document."""
    copy = await grunt.copy_doc(doc["doctype"], doc["name"])
    return {"message": _("Copy created: %(name)s") % {"name": copy["name"]}, "refresh": False}


@doc_action(
    "core.recalc",
    label="Recalculate",
    doctypes=["*"],
    icon="refresh-cw",
    variant="outline",
    confirm="Re-save the document? Formulas are recalculated and validate/before_save hooks run.",
)
async def recalc(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Re-save with no field changes so formulas and save-time hooks re-run.

    A validation error in the controller propagates to the client as-is.
    """
    await grunt.save_doc(doc["doctype"], doc["name"], {})
    return {"message": _("Document re-saved; formulas and hooks recalculated"), "refresh": True}


@doc_action(
    "core.copy_reference",
    label="Copy link",
    doctypes=["*"],
    icon="link",
    variant="ghost",
)
async def copy_reference(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Return a ``DocType/name`` reference string for the client to copy."""
    ref = f"{doc['doctype']}/{doc['name']}"
    return {"message": ref, "refresh": False, "copy": ref}


@doc_action(
    "trash.restore",
    label="Restore",
    doctypes=["DeletedDocument"],
    icon="undo-2",
    variant="success",
    roles=["System Manager"],
)
async def trash_restore(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Recreate the deleted document from its snapshot, keeping the original id."""
    from grunt.activity.doctypes.DeletedDocument.deleted_document import restore

    restored = await restore(doc["name"])
    return {"message": _("Restored: %(name)s") % {"name": restored["name"]}, "refresh": True}


@doc_action(
    "trash.restore_as_copy",
    label="Restore with a new ID",
    doctypes=["DeletedDocument"],
    icon="copy-plus",
    variant="outline",
    roles=["System Manager"],
)
async def trash_restore_as_copy(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Restore even when the original id is taken — a fresh id is generated."""
    from grunt.activity.doctypes.DeletedDocument.deleted_document import restore

    restored = await restore(doc["name"], allow_rename=True)
    return {"message": _("Restored as: %(name)s") % {"name": restored["name"]}, "refresh": True}


async def _set_todo_status(name: str, status: str) -> dict[str, Any]:
    """Flip a ToDo's status through the controller (stamps + notifications run)."""
    await grunt.save_doc("ToDo", name, {"status": status})
    return {"refresh": True}


@doc_action(
    "todo.complete",
    label="Mark as done",
    doctypes=["ToDo"],
    icon="check",
    variant="success",
)
async def todo_complete(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Close the task — the controller stamps completed_on/by and pings the assigner."""
    return {**await _set_todo_status(doc["name"], "Closed"), "message": _("Task completed")}


@doc_action(
    "todo.cancel",
    label="Cancel",
    doctypes=["ToDo"],
    icon="x",
    variant="ghost",
    confirm="Cancel the task?",
)
async def todo_cancel(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Cancel the task without marking it done."""
    return {**await _set_todo_status(doc["name"], "Cancelled"), "message": _("Task cancelled")}


@doc_action(
    "todo.reopen",
    label="Reopen",
    doctypes=["ToDo"],
    icon="undo-2",
    variant="outline",
)
async def todo_reopen(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Reopen a closed/cancelled task — the controller clears the completion stamp."""
    return {**await _set_todo_status(doc["name"], "Open"), "message": _("Task reopened")}


@doc_action(
    "report.send_now",
    label="Send now",
    doctypes=["Report"],
    icon="send",
    variant="outline",
    roles=["System Manager"],
    confirm="Send the report to its recipients now?",
)
async def report_send_now(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Email the report to its scheduled recipients right away."""
    from grunt.reports.delivery import send_report_now

    sent = await send_report_now(doc["name"])
    return {
        "message": _("Report queued for %(count)s recipients") % {"count": sent},
        "refresh": True,
    }
