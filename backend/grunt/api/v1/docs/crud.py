"""CRUD operations for Documents."""

from __future__ import annotations

import asyncio
import contextvars
from typing import Any

from fastapi import Body, Depends, HTTPException, Query, Request, status

from grunt.api.router import GruntRouter
from grunt.api.v1.docs.utils import get_doc_service
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt as grunt_app
from grunt.core.auth.dependencies import current_user
from grunt.core.doctypes.user.user import User
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
    user: User = Depends(current_user),
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

    result = await service.list_documents(
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
    return ok(**result.to_dict())


@router.post("/{doctype}", status_code=status.HTTP_201_CREATED)
async def create_document(
    doctype: str,
    body: dict[str, Any] = Body(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Create a new document."""
    doc = await grunt_app.new_doc(doctype, body)
    return ok(doc)


@router.get("/{doctype}/{doc_id}")
async def get_document(
    doctype: str,
    doc_id: str,
    user: User = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Get document data."""
    doc = await svc.get_document(doctype, doc_id, user)
    return ok(doc)


@router.put("/{doctype}/{doc_id}")
async def update_document(
    doctype: str,
    doc_id: str,
    body: dict[str, Any] = Body(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Update an existing document."""
    doc = await grunt_app.save_doc(doctype, doc_id, body)
    return ok(doc)


@router.delete("/{doctype}/{doc_id}")
async def delete_document(
    doctype: str,
    doc_id: str,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Delete a document."""
    await grunt_app.delete_doc(doctype, doc_id)
    return ok(message="Документ видалено")


@router.post("/{doctype}/bulk-delete", status_code=status.HTTP_202_ACCEPTED)
async def bulk_delete_documents(
    doctype: str,
    body: dict[str, Any] = Body(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Delete multiple documents by IDs, or all documents matching filters.

    Deletion runs as a background task; progress is pushed via WebSocket
    (event ``bulk_delete_progress`` / ``bulk_delete_done``) to the requesting user.

    Body variants:
      { "ids": ["id1", "id2"] }          — delete by explicit IDs
      { "delete_all": true, "filters": {"status__eq": "Draft"} }  — delete all matching
    """
    from grunt.api.v1.ws import manager  # noqa: PLC0415

    delete_all: bool = body.get("delete_all", False)

    if delete_all:
        raw_filters: dict[str, str] = body.get("filters", {}) or {}
        search: str | None = body.get("search") or None
        result = await grunt_app.get_list(
            doctype,
            filters=raw_filters if raw_filters else None,
            fields=["id"],
            limit=100_000,
            page=1,
            search=search,
        )
        ids: list[str] = [str(row["id"]) for row in result]
    else:
        ids = body.get("ids", [])
        if not ids:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="ids or delete_all is required"
            )

    total = len(ids)
    user_email = user.email
    engine = grunt_app._require_engine()

    async def _run() -> None:
        from grunt.core.db.session import async_session_factory  # noqa: PLC0415

        async def _progress(done: int, _total: int, error_count: int) -> None:
            await manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_progress",
                    "data": {"done": done, "total": _total, "errors": error_count},
                },
            )

        async with async_session_factory() as session:
            async with grunt_app.context(session, engine, user):
                deleted, errors = await grunt_app.bulk_delete_docs(
                    doctype,
                    ids,
                    progress_cb=_progress,
                )

        await manager.send_to_user(
            user_email,
            {
                "event": "bulk_delete_done",
                "data": {"deleted": deleted, "total": total, "errors": errors},
            },
        )

    asyncio.create_task(_run(), context=contextvars.Context())
    return ok({"started": True, "total": total})


@router.post("/{doctype}/bulk-update")
async def bulk_update_documents(
    doctype: str,
    body: dict[str, Any] = Body(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Update a single field on multiple documents."""
    ids: list[str] = body.get("ids", [])
    field: str | None = body.get("field")
    value: Any = body.get("value")

    if not ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="ids is required")
    if not field:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="field is required")

    updated = 0
    errors: list[str] = []
    for doc_id in ids:
        try:
            await grunt_app.save_doc(doctype, doc_id, {field: value})
            updated += 1
        except Exception as e:
            errors.append(f"{doc_id}: {e}")

    return ok({"updated": updated, "errors": errors})
