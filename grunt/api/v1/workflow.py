"""Workflow whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt.app import grunt as grunt_app
from grunt.metadata.registry import doctype_registry


@grunt.whitelist()
async def get_transitions(doctype: str, doc_id: str) -> list[dict[str, Any]]:
    """Return available workflow transitions for a document."""
    dt = await doctype_registry.get(doctype)
    from grunt.workflow.registry import get_active_workflow

    if not await get_active_workflow(doctype):
        return []

    from grunt.workflow.engine import workflow_engine

    doc = await grunt_app.get_doc(doctype, doc_id)
    user = grunt_app._require_user()
    transitions = await workflow_engine.get_available_transitions(dt, doc, user)
    return [{"action": t.action, "to_state": t.to_state} for t in transitions]


@grunt.whitelist()
async def apply_transition(doctype: str, doc_id: str, action: str) -> dict[str, Any]:
    """Apply a workflow transition to a document."""
    dt = await doctype_registry.get(doctype)
    from grunt.workflow.engine import workflow_engine

    user = grunt_app._require_user()
    session = grunt_app._require_session()
    engine = grunt_app._require_engine()

    updated = await workflow_engine.apply_transition(dt, doc_id, action, user, session, engine)
    return updated
