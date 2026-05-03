"""History and Activity operations for Documents."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt

router = GruntRouter(prefix="", tags=["docs", "history"])


@router.get("/{doctype}/{doc_id}/versions")
async def get_document_versions(
    doctype: str,
    doc_id: str,
) -> dict[str, Any]:
    """Return version history for a document."""
    # Ensure document exists and user has access
    await grunt.get_doc(doctype, doc_id)

    from grunt.document.versioning import version_service

    versions = await version_service.get_versions(grunt._require_session(), doctype, doc_id)
    return ok(versions)


@router.post("/{doctype}/{doc_id}/restore/{version_id}")
async def restore_document_version(
    doctype: str,
    doc_id: str,
    version_id: str,
) -> dict[str, Any]:
    """Restore a document to a previous version."""
    from grunt.document.versioning import version_service

    # Get current doc and verify access
    current_doc = await grunt.get_doc(doctype, doc_id)

    session = grunt._require_session()
    target = await version_service.get_version(session, version_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Версію не знайдено")
    if target["doctype"] != doctype or target["doc_id"] != doc_id:
        raise HTTPException(status_code=400, detail="Версія не належить цьому документу")

    # Get all versions for this doc
    all_versions = await version_service.get_versions(session, doctype, doc_id)

    # Build restore data
    restore_data = version_service.build_restore_data(current_doc, all_versions, target["version"])

    # Apply as a regular update
    dt = await grunt.get_meta(doctype)
    from grunt.metadata.field import NON_PHYSICAL_FIELDS

    update_fields = {}
    for field in dt.fields:
        if field.fieldtype in NON_PHYSICAL_FIELDS:
            continue
        if field.fieldname in restore_data:
            update_fields[field.fieldname] = restore_data[field.fieldname]

    result = await grunt.save_doc(doctype, doc_id, update_fields)

    # Add audit log
    await grunt.new_doc(
        "ActivityLog",
        {
            "doctype": doctype,
            "doc_id": doc_id,
            "action": "restore",
            "user": grunt.session.user,
            "details": f'{{"to_version": "{target["version"]}"}}',
        },
    )

    return ok(result, restored_to_version=target["version"])


@router.get("/{doctype}/{doc_id}/log")
async def get_document_log(
    doctype: str,
    doc_id: str,
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """Return the activity log for a document."""
    await grunt.get_doc(doctype, doc_id)

    entries = await grunt.get_list(
        "ActivityLog",
        filters={"doctype": doctype, "doc_id": doc_id},
        order_by="created_at",
        order="desc",
        limit=limit,
    )

    data = [
        {
            "id": str(e["id"]),
            "action": e.get("action"),
            "user": e.get("user"),
            "details": e.get("details"),
            "created_at": str(e["created_at"]) if e.get("created_at") else None,
        }
        for e in entries
    ]
    return ok(data)


@router.get("/{doctype}/{doc_id}/timeline")
async def get_document_timeline(
    doctype: str,
    doc_id: str,
) -> dict[str, Any]:
    """Return a merged timeline of activity and comments."""
    await grunt.get_doc(doctype, doc_id)  # permission check

    act_rows = await grunt.get_list(
        "ActivityLog", filters={"doctype": doctype, "doc_id": doc_id}, limit=1000
    )

    comment_rows = await grunt.get_list(
        "Comment", filters={"reference_doctype": doctype, "reference_id": doc_id}, limit=1000
    )

    items: list[dict[str, Any]] = []
    for r in act_rows:
        items.append(
            {
                "type": "activity",
                "id": str(r["id"]),
                "action": r.get("action"),
                "user": r.get("user"),
                "details": r.get("details"),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
            }
        )
    for r in comment_rows:
        items.append(
            {
                "type": "comment",
                "id": str(r["id"]),
                "content": r.get("content"),
                "comment_type": r.get("comment_type"),
                "user": r.get("owner"),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
            }
        )

    items.sort(key=lambda x: x["created_at"] or "")
    return ok(items)
