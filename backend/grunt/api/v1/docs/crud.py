"""CRUD operations for Documents."""

from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, HTTPException, Query, Request, status

from grunt.api.router import GruntRouter
from grunt.api.v1.docs.utils import _audit_log, get_doc_service
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.document.service import DocumentService

router = GruntRouter()


@router.get("/{doctype}")
async def list_documents(
    doctype: str,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=10000),
    sort_by: str = "modified_at",
    sort_order: str = "desc",
    search: str | None = None,
    fields: str | None = None,
    user: GruntUser = Depends(current_user),
    service: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """List documents for a DocType."""
    # Extract filter[field]=value from query params
    filters: dict[str, str] = {}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]"):
            filter_name = key[7:-1]
            filters[filter_name] = value

    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

    return await service.list_documents(
        doctype,
        user,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters if filters else None,
        search=search,
        fields=field_list,
    )


@router.post("/{doctype}", status_code=status.HTTP_201_CREATED)
async def create_document(
    doctype: str,
    body: dict[str, Any] = Body(...),
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Create a new document."""
    doc = await svc.create_document(doctype, body, user)
    await _audit_log(svc, doctype, str(doc.get("id", "")), "create", user)
    return {"success": True, "data": doc}


@router.get("/{doctype}/{doc_id}")
async def get_document(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Get document data."""
    doc = await svc.get_document(doctype, doc_id, user)
    return {"success": True, "data": doc}


@router.put("/{doctype}/{doc_id}")
async def update_document(
    doctype: str,
    doc_id: str,
    body: dict[str, Any] = Body(...),
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Update an existing document."""
    doc = await svc.update_document(doctype, doc_id, body, user)
    await _audit_log(svc, doctype, doc_id, "update", user, body)
    return {"success": True, "data": doc}


@router.delete("/{doctype}/{doc_id}")
async def delete_document(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Delete a document."""
    await svc.delete_document(doctype, doc_id, user)
    await _audit_log(svc, doctype, doc_id, "delete", user)
    return {"success": True, "message": "Документ видалено"}


@router.post("/{doctype}/bulk-delete")
async def bulk_delete_documents(
    doctype: str,
    body: dict[str, Any] = Body(...),
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Delete multiple documents by IDs."""
    ids: list[str] = body.get("ids", [])
    if not ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ids is required")

    deleted = 0
    errors: list[str] = []
    for doc_id in ids:
        try:
            await svc.delete_document(doctype, doc_id, user)
            await _audit_log(svc, doctype, doc_id, "delete", user)
            deleted += 1
        except Exception as e:
            errors.append(f"{doc_id}: {e}")

    return {"success": True, "data": {"deleted": deleted, "errors": errors}}


@router.post("/{doctype}/bulk-update")
async def bulk_update_documents(
    doctype: str,
    body: dict[str, Any] = Body(...),
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Update a single field on multiple documents."""
    ids: list[str] = body.get("ids", [])
    field: str | None = body.get("field")
    value: Any = body.get("value")

    if not ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ids is required")
    if not field:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="field is required")

    updated = 0
    errors: list[str] = []
    for doc_id in ids:
        try:
            await svc.update_document(doctype, doc_id, {field: value}, user)
            await _audit_log(
                svc, doctype, doc_id, "bulk_update", user, {"field": field, "value": value}
            )
            updated += 1
        except Exception as e:
            errors.append(f"{doc_id}: {e}")

    return {"success": True, "data": {"updated": updated, "errors": errors}}
