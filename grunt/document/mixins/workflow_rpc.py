"""Workflow RPC methods, exposed as static methods of ``Document``.

RPC: grunt.document.base.Document.get_workflow_transitions
RPC: grunt.document.base.Document.apply_workflow_transition
"""

from __future__ import annotations

from typing import Any

import grunt
from grunt import _


class DocumentWorkflowRPCMixin:
    """Workflow transitions on documents, exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def get_workflow_transitions(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return available workflow transitions for a document."""
        from grunt.errors import not_found

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        from grunt.workflow.registry import get_active_workflow

        if not await get_active_workflow(doctype):
            return []

        from grunt.workflow.engine import workflow_engine

        doc = await grunt.get_doc(doctype, doc_id)
        user = grunt.get_user()
        transitions = await workflow_engine.get_available_transitions(dt.doc, doc, user)
        return [
            {"action": t.action, "to_state": t.to_state, "prompt_fields": t.prompt_fields}
            for t in transitions
        ]

    @staticmethod
    @grunt.whitelist()
    async def apply_workflow_transition(
        doctype: str, doc_id: str, action: str, values: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Apply a workflow transition to a document.

        ``values`` fills in the transition's ``prompt_fields`` (e.g. a note
        entered in a dialog) — fields not declared on the transition are ignored.
        """
        from grunt.errors import not_found

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        from grunt.workflow.engine import workflow_engine

        user = grunt.get_user()
        session = grunt.get_session()

        return await workflow_engine.apply_transition(
            dt.doc, doc_id, action, user, session, grunt.get_engine(), values
        )
