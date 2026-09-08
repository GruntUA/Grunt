from __future__ import annotations

import hashlib
from typing import Any

from fastapi import HTTPException, Response, UploadFile

from grunt.api.context import whitelist
from grunt.app import grunt
from grunt.config import settings
from grunt.context import _user_ctx
from grunt.document.base import Document
from grunt.storage import get_storage_backend

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}


class File(Document):
    """DocType controller for File."""

    file_name: str
    file_url: str
    path: str
    content_type: str
    content_hash: str | None
    file_size: int
    uploaded_by: str
    is_public: bool
    thumbnail_url: str | None

    async def before_delete(self) -> None:
        """Delete the physical file before the DB row.

        Not best-effort: if the storage backend fails, the File document must
        not be deleted either — otherwise the row disappears while the
        physical file silently survives as an orphan with no record pointing
        to it. Letting the exception propagate aborts the whole delete
        pipeline (see ``DocumentWriteMixin.delete_document``).
        """
        if self.path:
            storage = get_storage_backend()
            await storage.delete(self.path)


@whitelist()
async def upload(
    file: UploadFile,
    attached_to_doctype: str | None = None,
    attached_to_id: str | None = None,
) -> dict[str, Any]:
    """Whitelisted method: Upload a file and create a File document."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            413,
            f"File too large (max {settings.max_upload_size_mb} MB)",
        )

    content_type = file.content_type or "application/octet-stream"
    content_hash = hashlib.sha256(content).hexdigest()

    # De-duplicate: a re-upload of the same name + byte-identical content by the
    # same user for the same target reuses the existing File instead of storing a
    # second copy. Scoped tightly (name, hash, size, uploader, attachment target)
    # so a different name — or the same bytes for a *different* document — still
    # gets its own correctly-linked row.
    existing = await File.objects.filter(
        file_name=file.filename,
        content_hash=content_hash,
        file_size=len(content),
        uploaded_by=grunt.session.user,
        attached_to_doctype=attached_to_doctype or None,
        attached_to_id=attached_to_id or None,
    ).first()
    if existing is not None:
        return _upload_payload(existing, deduped=True)

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

    # Create the File document first to get the auto-generated name.
    file_doc = await File.objects.create(
        file_name=file.filename,
        file_url="",  # placeholder; updated below with the real name
        path=path,
        content_type=content_type,
        content_hash=content_hash,
        file_size=len(content),
        uploaded_by=grunt.session.user,
        is_public=True,
        attached_to_doctype=attached_to_doctype or None,
        attached_to_id=attached_to_id or None,
    )
    file_id = str(file_doc.name)

    # Build URL using the document name and persist it.
    file_url = f"/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id={file_id}"
    update: dict[str, Any] = {"file_url": file_url}
    if is_image:
        update["thumbnail_url"] = file_url
    await grunt.save_doc("File", file_id, update)
    file_doc.file_url = file_url

    return _upload_payload(file_doc, deduped=False)


def _upload_payload(doc: File, *, deduped: bool) -> dict[str, Any]:
    """Response shape shared by a fresh upload and a de-duplicated hit."""
    return {
        "id": str(doc.name),
        "url": doc.file_url,
        "filename": doc.file_name,
        "content_type": doc.content_type,
        "size_bytes": doc.file_size,
        "deduped": deduped,
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

    from urllib.parse import quote

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
    search: str = "",
    limit: int = 50,
    page: int = 1,
    order_by: str = "created_at",
    order: str = "desc",
) -> dict[str, Any]:
    """Whitelisted method: List files.

    ``search`` does a case-insensitive substring match on the file name;
    ``filters`` is a raw operator-aware filter dict (e.g.
    ``{"content_type__in": [...], "attached_to_doctype": "..."}``).
    """
    all_filters = dict(filters or {})
    if search.strip():
        all_filters["file_name__ilike"] = search.strip()
    query = File.objects.filter(**all_filters)
    query = query.order_by(f"-{order_by}" if order == "desc" else order_by)
    records = await query.limit(limit).page(page).all()
    total = await query.count()

    return {
        "items": [
            {
                "name": str(r.name),
                "url": r.file_url,
                "filename": r.file_name,
                "content_type": r.content_type,
                "size_bytes": r.file_size,
                "created_at": str(r.created_at) if r.created_at else None,
                "uploaded_by": r.uploaded_by,
            }
            for r in records
        ],
        "total": total,
    }


@whitelist()
async def remove(file_id: str) -> bool:
    """Whitelisted method: Delete a file.

    Deletes only through grunt.delete_doc(), not a manual storage.delete()
    here first — that used to run unconditionally via grunt.db (which
    bypasses permission checks) *before* delete_doc()'s own guard had a
    chance to reject the request, so a non-owner could destroy someone
    else's file's actual content even though the DB row deletion would
    correctly be denied. File.before_delete() already deletes the physical
    file as a required (non-best-effort) step of the guarded pipeline.
    """
    await grunt.delete_doc("File", file_id)
    return True
