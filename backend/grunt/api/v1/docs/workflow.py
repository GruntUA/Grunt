"""Workflow operations for Documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends

from grunt.api.v1.docs.utils import get_doc_service
from grunt.core.auth.dependencies import current_user
from grunt.core.db.session import get_engine, get_session
from grunt.core.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser
    from grunt.core.document.service import DocumentService

router = APIRouter()


@router.post("/{doctype}/{doc_id}/transition")
async def apply_workflow_transition(
    doctype: str,
    doc_id: str,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    eng: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Apply a workflow transition to a document."""
    dt = await doctype_registry.get(doctype)
    from grunt.core.workflow.engine import workflow_engine  # noqa: PLC0415

    updated = await workflow_engine.apply_transition(dt, doc_id, body["action"], user, session, eng)
    return {"success": True, "data": updated}


@router.get("/{doctype}/{doc_id}/transitions")
async def get_workflow_transitions(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Return available workflow transitions for a document."""
    dt = await doctype_registry.get(doctype)
    if not dt.workflow:
        return {"success": True, "data": []}

    from grunt.core.workflow.engine import workflow_engine  # noqa: PLC0415

    doc = await svc.get_document(doctype, doc_id, user)
    transitions = await workflow_engine.get_available_transitions(dt, doc, user)
    return {
        "success": True,
        "data": [{"action": t.action, "to_state": t.to_state} for t in transitions],
    }
