"""Document API endpoints — dynamic CRUD for any DocType."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import engine as _engine
from grunt.core.db.session import get_session
from grunt.core.document.service import DocumentService

router = APIRouter()


async def get_engine() -> AsyncEngine:
    return _engine


def get_doc_service(
    session: AsyncSession = Depends(get_session),
    eng: AsyncEngine = Depends(get_engine),
) -> DocumentService:
    return DocumentService(session, eng)


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/{doctype}")
async def list_documents(
    doctype: str,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    sort: str = "modified_at",
    order: str = "desc",
    search: str | None = None,
    fields: str | None = None,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    # Extract filter[field]=value from query params
    filters: dict[str, str] = {}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]"):
            filter_name = key[7:-1]
            filters[filter_name] = value

    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

    return await svc.list_documents(
        doctype_name=doctype,
        user=user,
        page=page,
        per_page=per_page,
        sort_by=sort,
        sort_order=order,
        filters=filters if filters else None,
        search=search,
        fields=field_list,
    )


@router.post("/{doctype}", status_code=status.HTTP_201_CREATED)
async def create_document(
    doctype: str,
    body: dict[str, Any],
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    doc = await svc.create_document(doctype, body, user)
    return {"success": True, "data": doc}


@router.get("/{doctype}/{doc_id}")
async def get_document(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    doc = await svc.get_document(doctype, doc_id, user)
    return {"success": True, "data": doc}


@router.put("/{doctype}/{doc_id}")
async def update_document(
    doctype: str,
    doc_id: str,
    body: dict[str, Any],
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    doc = await svc.update_document(doctype, doc_id, body, user)
    return {"success": True, "data": doc}


@router.delete("/{doctype}/{doc_id}")
async def delete_document(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    await svc.delete_document(doctype, doc_id, user)
    return {"success": True, "message": "Документ видалено"}
