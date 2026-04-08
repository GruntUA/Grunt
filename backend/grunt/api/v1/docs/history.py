"""History and Activity operations for Documents."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.document.service import DocumentService
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry
from grunt.api.v1.docs.utils import get_doc_service, _audit_log

router = APIRouter()


@router.get("/{doctype}/{doc_id}/versions")
async def get_document_versions(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Return version history for a document."""
    # Ensure document exists
    await svc.get_document(doctype, doc_id, user)

    from grunt.core.document.versioning import version_service  # noqa: PLC0415

    versions = await version_service.get_versions(session, doctype, doc_id)
    return {"success": True, "data": versions}


@router.post("/{doctype}/{doc_id}/restore/{version_id}")
async def restore_document_version(
    doctype: str,
    doc_id: str,
    version_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Restore a document to a previous version."""
    from grunt.core.document.versioning import version_service  # noqa: PLC0415

    # Get current doc
    current_doc = await svc.get_document(doctype, doc_id, user)

    # Get target version
    target = await version_service.get_version(session, version_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Версію не знайдено")
    if target["doctype"] != doctype or target["doc_id"] != doc_id:
        raise HTTPException(status_code=400, detail="Версія не належить цьому документу")

    # Get all versions for this doc
    all_versions = await version_service.get_versions(session, doctype, doc_id)

    # Build restore data
    restore_data = version_service.build_restore_data(
        current_doc, all_versions, target["version"]
    )

    # Apply as a regular update
    dt = await doctype_registry.get(doctype)
    from grunt.core.metadata.field import NON_PHYSICAL_FIELDS  # noqa: PLC0415

    update_fields = {}
    for field in dt.fields:
        if field.fieldtype in NON_PHYSICAL_FIELDS:
            continue
        if field.fieldname in restore_data:
            update_fields[field.fieldname] = restore_data[field.fieldname]

    result = await svc.update_document(doctype, doc_id, update_fields, user)
    await _audit_log(svc, doctype, doc_id, "restore", user, {"to_version": target["version"]})

    return {"success": True, "data": result, "restored_to_version": target["version"]}


@router.get("/{doctype}/{doc_id}/log")
async def get_document_log(
    doctype: str,
    doc_id: str,
    limit: int = Query(10, ge=1, le=100),
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the activity log for a document."""
    table = compile_doctype_to_table(doctype_registry._doctypes["ActivityLog"])
    q = (
        select(table)
        .where(
            table.c.doctype == doctype,
            table.c.doc_id == doc_id,
        )
        .order_by(desc(table.c.created_at))
        .limit(limit)
    )
    result = await session.execute(q)
    entries = result.mappings().all()
    data = [
        {
            "id": e["id"],
            "action": e["action"],
            "user": e["user"],
            "details": e["details"],
            "created_at": e["created_at"].isoformat() if e["created_at"] else None,
        }
        for e in entries
    ]
    return {"success": True, "data": data}


@router.get("/{doctype}/{doc_id}/timeline")
async def get_document_timeline(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return a merged timeline of activity and comments."""
    await svc.get_document(doctype, doc_id, user)  # permission check

    activity_table = compile_doctype_to_table(doctype_registry._doctypes["ActivityLog"])
    comment_table = compile_doctype_to_table(doctype_registry._doctypes["Comment"])

    act_rows = (
        await session.execute(
            select(activity_table)
            .where(activity_table.c.doctype == doctype, activity_table.c.doc_id == doc_id)
        )
    ).mappings().all()

    comment_rows = (
        await session.execute(
            select(comment_table)
            .where(comment_table.c.reference_doctype == doctype, comment_table.c.reference_id == doc_id)
        )
    ).mappings().all()

    items: list[dict[str, Any]] = []
    for r in act_rows:
        items.append({
            "type": "activity",
            "id": str(r["id"]),
            "action": r["action"],
            "user": r["user"],
            "details": r["details"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    for r in comment_rows:
        items.append({
            "type": "comment",
            "id": str(r["id"]),
            "content": r["content"],
            "comment_type": r["comment_type"],
            "user": r["owner"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })

    items.sort(key=lambda x: x["created_at"] or "")
    return {"success": True, "data": items}
