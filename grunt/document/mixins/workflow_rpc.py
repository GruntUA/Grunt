"""Workflow RPC methods, exposed as static methods of ``Document``.

RPC: grunt.document.base.Document.get_workflow_transitions
RPC: grunt.document.base.Document.apply_workflow_transition
"""

from __future__ import annotations

from typing import Any

import grunt
from grunt.metadata.registry import doctype_registry


class DocumentWorkflowRPCMixin:
    """Workflow transitions on documents, exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def get_workflow_transitions(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return available workflow transitions for a document."""
        from grunt.app import grunt as grunt_app

        dt = await doctype_registry.get(doctype)
        from grunt.workflow.registry import get_active_workflow

        if not await get_active_workflow(doctype):
            return []

        from grunt.workflow.engine import workflow_engine

        doc = await grunt_app.get_doc(doctype, doc_id)
        user = grunt_app._require_user()
        transitions = await workflow_engine.get_available_transitions(dt, doc, user)
        return [{"action": t.action, "to_state": t.to_state} for t in transitions]

    @staticmethod
    @grunt.whitelist()
    async def apply_workflow_transition(doctype: str, doc_id: str, action: str) -> dict[str, Any]:
        """Apply a workflow transition to a document."""
        from grunt.app import grunt as grunt_app

        dt = await doctype_registry.get(doctype)
        from grunt.workflow.engine import workflow_engine

        user = grunt_app._require_user()
        session = grunt_app._require_session()

        return await workflow_engine.apply_transition(
            dt, doc_id, action, user, session, grunt_app._require_engine()
        )
