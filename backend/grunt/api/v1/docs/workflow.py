"""Workflow operations for Documents."""

from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, HTTPException

from grunt.api.router import GruntRouter
from grunt.app import grunt
from grunt.core.metadata.registry import doctype_registry

router = GruntRouter(prefix="", tags=["docs", "workflow"])


@router.get("/{doctype}/{doc_id}/transitions")
async def get_document_transitions(
    doctype: str,
    doc_id: str,
) -> dict[str, Any]:
    """Return available workflow transitions for a document."""
    dt = await doctype_registry.get(doctype)
    if not dt.workflow:
        return {"success": True, "data": []}

    from grunt.core.workflow.engine import workflow_engine

    doc = await grunt.get_doc(doctype, doc_id)
    user = grunt._require_user()
    transitions = await workflow_engine.get_available_transitions(dt, doc, user)
    return {
        "success": True,
        "data": [{"action": t.action, "to_state": t.to_state} for t in transitions],
    }


@router.post("/{doctype}/{doc_id}/transition")
async def apply_workflow_transition(
    doctype: str,
    doc_id: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Apply a workflow transition to a document."""
    dt = await doctype_registry.get(doctype)
    from grunt.core.workflow.engine import workflow_engine

    user = grunt._require_user()
    session = grunt._require_session()

    updated = await workflow_engine.apply_transition(
        dt, doc_id, body["action"], user, session, session.bind
    )
    return {"success": True, "data": updated}
