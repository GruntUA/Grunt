"""File upload / download API — Strictly DocType-driven."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response

from grunt.app import grunt
from grunt.config import settings
from grunt.core.auth.dependencies import current_user
from grunt.core.db.session import get_engine, get_session
from grunt.core.document.registry import document_registry
from grunt.core.storage import get_storage_backend

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser

router = APIRouter()

MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}


@router.post("/", include_in_schema=False)
@router.post("")
async def upload_file(
    file: UploadFile,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
):
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

    # Create the File DocType record directly
    path.split("/")[-1]
    is_image = content_type in _IMAGE_TYPES

    _tokens = grunt.set_context(session, engine, user)
    try:
        # Use controller to create the record
        file_doctype = document_registry.get("File")
        file_doc = file_doctype(
            "File",
            {
                "file_name": file.filename,
                "path": path,
                "content_type": content_type,
                "file_size": len(content),
                "uploaded_by": user.id,
                "is_public": True,
            },
            user,
            session,
        )

        await file_doc.insert()

        # Update URL with the generated ID
        file_url = f"/api/v1/files/{file_doc.id}"
        file_doc.file_url = file_url
        if is_image:
            file_doc.thumbnail_url = file_url

        await file_doc.save()

        return {
            "success": True,
            "data": {
                "id": file_doc.id,
                "url": file_url,
                "filename": file_doc.file_name,
                "content_type": file_doc.content_type,
                "size_bytes": file_doc.file_size,
            },
        }
    finally:
        grunt.reset_context(_tokens)


@router.get("/", include_in_schema=False)
@router.get("")
async def list_files(
    limit: int = 50,
    offset: int = 0,
    search: str | None = Query(None),
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
):
    """List files using File DocType."""
    _tokens = grunt.set_context(session, engine, user)
    try:
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
            order_by="created_at desc",
            limit=limit,
            offset=offset,
        )

        # Get total count
        total = await grunt.db.count("File", filters=filters)

        data = [
            {
                "id": r["id"],
                "url": r["file_url"],
                "filename": r["file_name"],
                "content_type": r["content_type"],
                "size_bytes": r["file_size"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "uploaded_by": r["uploaded_by"],
            }
            for r in records
        ]

        return {
            "success": True,
            "data": data,
            "total": total,
        }
    finally:
        grunt.reset_context(_tokens)


@router.get("/{file_id}")
async def get_file(
    file_id: str,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
):
    """Download / serve a file using File DocType metadata."""
    # Note: We use system user here because file access might be public or bypass normal RBAC in some cases
    # For now, let's just stick to the session
    _tokens = grunt.set_context(session, engine, None)
    try:
        try:
            doc = await grunt.get_doc("File", file_id)
        except Exception:
            raise HTTPException(404, "File not found") from None

        storage = get_storage_backend()
        try:
            content = await storage.get(doc.path)
        except Exception:
            raise HTTPException(404, "File not found on storage") from None

        return Response(
            content=content,
            media_type=doc.content_type,
            headers={"Content-Disposition": f'attachment; filename="{doc.file_name}"'},
        )
    finally:
        grunt.reset_context(_tokens)


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
):
    """Delete a file using File DocType."""
    _tokens = grunt.set_context(session, engine, user)
    try:
        try:
            doc_data = await grunt.get_doc("File", file_id)
            file_doctype = document_registry.get("File")
            doc = file_doctype("File", doc_data, user, session)
        except Exception:
            raise HTTPException(status_code=404, detail="File metadata not found") from None

        # Delete from storage
        storage = get_storage_backend()
        await storage.delete(doc.path)

        # Delete DocType record
        await doc.delete()

        return {"success": True, "data": {"id": file_id}}
    finally:
        grunt.reset_context(_tokens)
