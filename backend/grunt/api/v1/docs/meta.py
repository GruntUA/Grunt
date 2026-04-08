"""Metadata operations for Documents (Links)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends

from grunt.api.v1.docs.utils import get_doc_service
from grunt.core.auth.dependencies import current_user
from grunt.core.db.session import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.core.auth.models import GruntUser
    from grunt.core.document.service import DocumentService

router = APIRouter()


@router.get("/{doctype}/{doc_id}/links")
async def get_document_links(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Return all documents that link to this document (backlinks)."""
    await svc.get_document(doctype, doc_id, user)

    from grunt.core.document.links import link_service  # noqa: PLC0415

    links = await link_service.get_backlinks(session, doctype, doc_id)
    return {"success": True, "data": links}
