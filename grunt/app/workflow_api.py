"""Workflow transitions for the GruntApp facade (``grunt.submit``)."""

from typing import Any

from grunt.errors import not_found
from grunt.i18n import _
from grunt.local import require_engine, require_session, require_session_user
from grunt.metadata.registry import doctype_registry
from grunt.workflow.engine import workflow_engine


class WorkflowAPI:
    async def submit(
        self,
        doctype: str,
        doc_id: str,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply a workflow transition to a document.

        ``action`` must match a transition label defined in the DocType's workflow.
        Raises ``HTTPException(409)`` if the transition is not available for the
        current document state or the user lacks the required role::

            await grunt.submit("LeaveRequest", request_id, "Approve")

        ``values`` fills in the transition's ``prompt_fields`` (e.g. a note
        collected in a dialog before applying the transition).
        """
        dt = await doctype_registry.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        return await workflow_engine.apply_transition(
            dt.doc,
            doc_id,
            action,
            require_session_user(),
            require_session(),
            require_engine(),
            values,
        )
