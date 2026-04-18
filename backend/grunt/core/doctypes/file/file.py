from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Response, UploadFile

from grunt.api.context import whitelist
from grunt.app import grunt
from grunt.config import settings
from grunt.core.context import _user_ctx
from grunt.core.document.base import Document
from grunt.core.storage import get_storage_backend

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}


class File(Document):
    """DocType controller for File."""

    file_name: str
    file_url: str
    path: str
    content_type: str
    file_size: int
    uploaded_by: str
    is_public: bool
    thumbnail_url: str | None

    async def before_delete(self) -> None:
        if self.path:
            storage = get_storage_backend()
            try:
                await storage.delete(self.path)
            except Exception:
                pass


@whitelist()
async def upload(file: UploadFile) -> dict[str, Any]:
    """Whitelisted method: Upload a file and create a File document."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            413,
            f"File too large (max {grunt.settings.max_upload_size_mb} MB)",
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

    # Generate the whitelisted method URL for this file.
    file_id = str(uuid.uuid4())
    file_url = f"/api/v1/method/grunt.core.doctypes.file.file.get_content?file_id={file_id}"

    doc_data: dict[str, Any] = {
        "id": file_id,
        "file_name": file.filename,
        "file_url": file_url,
        "path": path,
        "content_type": content_type,
        "file_size": len(content),
        "uploaded_by": grunt.session.user,
        "is_public": True,
    }
    if is_image:
        doc_data["thumbnail_url"] = file_url

    file_doc = await grunt.new_doc("File", doc_data)

    return {
        "id": file_id,
        "url": file_url,
        "filename": file_doc.get("file_name"),
        "content_type": file_doc.get("content_type"),
        "size_bytes": file_doc.get("file_size"),
    }


@whitelist(allow_guest=True)
async def get_content(file_id: str) -> Response:
    """Whitelisted method: Fetch file content from storage."""
    # Use grunt.db directly to avoid permission checks that require an active user.
    doc = await grunt.db.get_values(
        "File", file_id, ["path", "content_type", "file_name", "is_public"]
    )
    if not doc:
        raise HTTPException(404, "File not found")

    # If file is not public, require the user to be authenticated
    if not doc.get("is_public") and _user_ctx.get() is None:
        raise HTTPException(401, "Authentication required to access this file")

    storage = get_storage_backend()
    try:
        file_path = doc.get("path") or ""
        content = await storage.get(file_path)
    except Exception:
        raise HTTPException(404, "File not found on storage") from None

    from urllib.parse import quote  # noqa: PLC0415

    file_name = doc.get("file_name") or "file"
    # RFC 5987: UTF-8 encoded filename for non-ASCII characters
    encoded_name = quote(file_name, safe="")
    disposition = f"attachment; filename*=UTF-8''{encoded_name}"

    return Response(
        content=content,
        media_type=doc.get("content_type"),
        headers={"Content-Disposition": disposition},
    )


@whitelist()
async def get_list(
    filters: dict[str, Any] | None = None,
    limit: int = 50,
    page: int = 1,
    order_by: str = "created_at",
    order: str = "desc",
) -> dict[str, Any]:
    """Whitelisted method: List files."""
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
        order_by=order_by,
        order=order,
        limit=limit,
        page=page,
    )
    total = await grunt.count("File", filters=filters)

    return {
        "items": [
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
        ],
        "total": total,
    }


@whitelist()
async def remove(file_id: str) -> bool:
    """Whitelisted method: Delete a file."""
    doc = await grunt.db.get_values("File", file_id, ["path"])
    if not doc:
        raise HTTPException(404, "File not found")

    storage = get_storage_backend()
    await storage.delete(doc.get("path") or "")
    await grunt.delete_doc("File", file_id)
    return True
