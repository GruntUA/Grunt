"""Built-in document actions shipped with core.

Generic, DocType-agnostic (``doctypes=["*"]``) — they stay invisible until an
admin binds one from a DocType's **Actions** tab. Handy as ready-made buttons
and as worked examples of the ``@doc_action`` contract.

`run()` guarantees ``doc["doctype"]`` and ``doc["name"]`` are always set.
"""

from __future__ import annotations

from typing import Any

import structlog

import grunt
from grunt.actions.registry import doc_action

logger = structlog.get_logger()


@doc_action(
    "core.duplicate",
    label="Дублювати",
    doctypes=["*"],
    icon="copy",
    variant="outline",
)
async def duplicate(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Create a fresh copy of the current document."""
    copy = await grunt.copy_doc(doc["doctype"], doc["name"])
    return {"message": f"Створено копію: {copy['name']}", "refresh": False}


@doc_action(
    "core.recalc",
    label="Перерахувати",
    doctypes=["*"],
    icon="refresh-cw",
    variant="outline",
    confirm="Перезберегти документ? Перерахуються формули й запустяться хуки validate/before_save.",
)
async def recalc(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Re-save with no field changes so formulas and save-time hooks re-run.

    A validation error in the controller propagates to the client as-is.
    """
    await grunt.save_doc(doc["doctype"], doc["name"], {})
    return {"message": "Документ перезбережено, формули та хуки перераховано", "refresh": True}


@doc_action(
    "core.copy_reference",
    label="Скопіювати посилання",
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
    label="Відновити",
    doctypes=["DeletedDocument"],
    icon="undo-2",
    variant="success",
    roles=["System Manager"],
)
async def trash_restore(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Recreate the deleted document from its snapshot, keeping the original id."""
    from grunt.activity.doctypes.DeletedDocument.deleted_document import restore

    restored = await restore(doc["name"])
    return {"message": f"Відновлено: {restored['name']}", "refresh": True}


@doc_action(
    "trash.restore_as_copy",
    label="Відновити з новим ID",
    doctypes=["DeletedDocument"],
    icon="copy-plus",
    variant="outline",
    roles=["System Manager"],
)
async def trash_restore_as_copy(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Restore even when the original id is taken — a fresh id is generated."""
    from grunt.activity.doctypes.DeletedDocument.deleted_document import restore

    restored = await restore(doc["name"], allow_rename=True)
    return {"message": f"Відновлено як: {restored['name']}", "refresh": True}


async def _set_todo_status(name: str, status: str) -> dict[str, Any]:
    """Flip a ToDo's status through the controller (stamps + notifications run)."""
    await grunt.save_doc("ToDo", name, {"status": status})
    return {"refresh": True}


@doc_action(
    "todo.complete",
    label="Позначити виконаним",
    doctypes=["ToDo"],
    icon="check",
    variant="success",
)
async def todo_complete(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Close the task — the controller stamps completed_on/by and pings the assigner."""
    return {**await _set_todo_status(doc["name"], "Closed"), "message": "Завдання виконано"}


@doc_action(
    "todo.cancel",
    label="Скасувати",
    doctypes=["ToDo"],
    icon="x",
    variant="ghost",
    confirm="Скасувати завдання?",
)
async def todo_cancel(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Cancel the task without marking it done."""
    return {**await _set_todo_status(doc["name"], "Cancelled"), "message": "Завдання скасовано"}


@doc_action(
    "todo.reopen",
    label="Відкрити знову",
    doctypes=["ToDo"],
    icon="undo-2",
    variant="outline",
)
async def todo_reopen(doc: dict[str, Any], *, args: dict[str, Any]) -> dict[str, Any]:
    """Reopen a closed/cancelled task — the controller clears the completion stamp."""
    return {**await _set_todo_status(doc["name"], "Open"), "message": "Завдання відкрито"}
