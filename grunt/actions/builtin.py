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
    copy = await grunt.duplicate(doc["doctype"], doc["name"])
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
