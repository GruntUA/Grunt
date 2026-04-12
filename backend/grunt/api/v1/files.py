"""File upload / download API — Strictly DocType-driven."""

from __future__ import annotations

from typing import Any

from fastapi import File, HTTPException, Query, Response, UploadFile

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.config import settings
from grunt.core.storage import get_storage_backend

router = GruntRouter(prefix="", tags=["files"])

MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}


@router.post("/", include_in_schema=False)
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload a file using the File DocType."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            413,
            f"File too large (max {settings.max_upload_size_mb} MB)",
        )

    content_type = file.content_type or "application/octet-stream"
    storage = get_storage_backend()

    try:
        path = await storage.save(
            content=content,
            filename=file.filename,
            content_type=content_type,
        )
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc

    is_image = content_type in _IMAGE_TYPES

    user = grunt.session
    # Use GruntApp SDK to create the record
    file_doc = await grunt.new_doc(
        "File",
        {
            "file_name": file.filename,
            "path": path,
            "content_type": content_type,
            "file_size": len(content),
            "uploaded_by": user.user,
            "is_public": True,
        },
    )

    # Update URL with the generated ID
    file_id = str(file_doc.get("id"))
    file_url = f"/api/v1/files/{file_id}"
    update_data = {"file_url": file_url}
    if is_image:
        update_data["thumbnail_url"] = file_url

    await grunt.save_doc("File", file_id, update_data)

    return {
        "success": True,
        "data": {
            "id": file_id,
            "url": file_url,
            "filename": file_doc.get("file_name"),
            "content_type": file_doc.get("content_type"),
            "size_bytes": file_doc.get("file_size"),
        },
    }


@router.get("/", include_in_schema=False)
@router.get("")
async def list_files(
    limit: int = 50,
    offset: int = 0,
    search: str | None = Query(None),
):
    """List files using File DocType."""
    filters = {}
    if search:
        filters["file_name"] = ["like", f"%{search}%"]

    records = await grunt.get_list(
        "File",
        filters=filters,
        fields=[
            "id",
            "file_name",
            "file_url",
            "content_type",
            "file_size",
            "created_at",
            "uploaded_by",
        ],
        order_by="created_at",
        order="desc",
        limit=limit,
        page=max(1, offset // limit + 1) if limit else 1,
    )

    # Get total count
    total = await grunt.count("File", filters=filters)

    data = [
        {
            "id": str(r["id"]),
            "url": r.get("file_url"),
            "filename": r.get("file_name"),
            "content_type": r.get("content_type"),
            "size_bytes": r.get("file_size"),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
            "uploaded_by": r.get("uploaded_by"),
        }
        for r in records
    ]

    return {
        "success": True,
        "data": data,
        "total": total,
    }


@router.get("/{file_id}")
async def get_file_metadata(
    file_id: str,
) -> Response:
    """Download / serve a file using File DocType metadata."""
    try:
        doc = await grunt.get_doc("File", file_id)
    except Exception:
        raise HTTPException(404, "File not found") from None

    storage = get_storage_backend()
    try:
        file_path = doc.get("path") or ""
        content = await storage.get(file_path)
    except Exception:
        raise HTTPException(404, "File not found on storage") from None

    return Response(
        content=content,
        media_type=doc.get("content_type"),
        headers={"Content-Disposition": f'attachment; filename="{doc.get("file_name")}"'},
    )


@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
) -> Response:
    """Download a file with attachment disposition."""
    return await get_file_metadata(file_id)


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
) -> dict[str, Any]:
    """Delete a file using File DocType."""
    try:
        doc = await grunt.get_doc("File", file_id)
    except Exception:
        raise HTTPException(status_code=404, detail="File metadata not found") from None

    # Delete from storage first
    storage = get_storage_backend()
    await storage.delete(doc.get("path") or "")

    # Delete DocType record
    await grunt.delete_doc("File", file_id)

    return ok({"id": file_id})
