"""Workflow whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt import _
from grunt.errors import not_found
from grunt.workflow.engine import workflow_engine
from grunt.workflow.registry import get_active_workflow


@grunt.whitelist()
async def get_transitions(doctype: str, doc_id: str) -> list[dict[str, Any]]:
    """Return available workflow transitions for a document."""
    dt = await grunt.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})

    if not await get_active_workflow(doctype):
        return []

    doc = await grunt.get_doc(doctype, doc_id)
    user = grunt.get_user()
    transitions = await workflow_engine.get_available_transitions(dt.doc, doc, user)
    return [
        {
            "action": t.action,
            "to_state": t.to_state,
            "prompt_fields": t.prompt_fields,
            "require_comment": t.require_comment,
        }
        for t in transitions
    ]


@grunt.whitelist()
async def apply_transition(
    doctype: str, doc_id: str, action: str, values: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Apply a workflow transition to a document."""
    dt = await grunt.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})

    user = grunt.get_user()
    session = grunt.get_session()
    engine = grunt.get_engine()

    updated = await workflow_engine.apply_transition(
        dt.doc, doc_id, action, user, session, engine, values
    )
    return updated
