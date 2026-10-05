from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

import grunt
from grunt import _
from grunt.api.context import whitelist
from grunt.document.base import Document
from grunt.local import _user_ctx
from grunt.storage import files
from grunt.storage.backends import FileTooLargeError, get_storage_backend
from grunt.storage.thumbnails import THUMB_MIMETYPE, can_thumbnail


class File(Document):
    """DocType controller for File.

    A row is metadata over a content-addressed blob (``content_hash``): the
    blob outlives the row and is dropped by the storage garbage collector
    (grunt.storage.gc) once nothing - trash included - refers to it.
    """

    file_name: str
    file_url: str
    content_type: str
    content_hash: str
    file_size: int
    uploaded_by: str
    is_public: bool
    thumbnail_url: str | None
    attached_to_doctype: str | None
    attached_to_id: str | None
    folder: str | None


@whitelist()
async def upload(
    file: UploadFile,
    attached_to_doctype: str | None = None,
    attached_to_id: str | None = None,
    is_public: bool | None = None,
    folder: str | None = None,
) -> dict[str, Any]:
    """Whitelisted method: Upload a file and create a File document.

    An attachment (``attached_to_*`` set) is private unless ``is_public`` is
    passed explicitly or its DocType sets ``public_attachments`` - readable
    only with its document, via a signed URL (see :mod:`grunt.storage.signing`).
    A free-standing library file stays public; ``folder`` files it into the
    library tree (FileFolder).
    """
    if is_public is None:
        meta = await grunt.get_meta(attached_to_doctype) if attached_to_doctype else None
        is_public = not attached_to_doctype or bool(meta and meta.public_attachments)
    if not file.filename:
        raise HTTPException(400, _("No filename provided"))

    content_type = file.content_type or "application/octet-stream"
    try:
        files.validate_mime_type(content_type)
        # Streamed to disk while hashing - never held in memory whole.
        key, size = await get_storage_backend().put(file.file, max_bytes=files.upload_limit())
    except FileTooLargeError:
        from grunt.config import settings

        raise HTTPException(
            413,
            _("The file is too large (max %(size)s MB)") % {"size": settings.max_upload_size_mb},
        ) from None
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    finally:
        await file.close()

    # The blob is stored once whatever happens; this only decides whether a
    # re-upload of the same name + bytes by the same user for the same target
    # reuses its File row instead of listing a second one. A different name -
    # or the same bytes for a *different* document - gets its own row.
    existing = await File.objects.filter(
        file_name=file.filename,
        content_hash=key,
        uploaded_by=grunt.get_user().email,
        attached_to_doctype=attached_to_doctype or None,
        attached_to_id=attached_to_id or None,
        folder=folder or None,
    ).first()
    if existing is not None:
        return _upload_payload(existing.as_dict(), deduped=True)

    doc = await files.create_file(
        key,
        size,
        file.filename,
        content_type,
        attached_to_doctype=attached_to_doctype,
        attached_to_id=attached_to_id,
        folder=folder,
        is_public=is_public,
    )
    return _upload_payload(doc, deduped=False)


def _upload_payload(doc: dict[str, Any], *, deduped: bool) -> dict[str, Any]:
    """Response shape shared by a fresh upload and a de-duplicated hit."""
    return {
        "id": str(doc["name"]),
        "url": doc["file_url"],
        "filename": doc["file_name"],
        "content_type": doc["content_type"],
        "size_bytes": doc["file_size"],
        "thumbnail_url": doc.get("thumbnail_url"),
        "deduped": deduped,
    }


async def generate_missing_thumbnails(limit: int = 500) -> int:
    """Backfill previews for files that have none (made before, or on a failure)."""
    rows = await grunt.db.get_all(
        "File",
        filters={"thumbnail_url__isnull": True},
        fields=["name", "content_hash", "content_type"],
        limit=None,
    )
    made = 0
    for row in rows:
        if made >= limit:
            break
        key, ctype = row.get("content_hash"), row.get("content_type")
        if not key or not can_thumbnail(ctype) or not await files.ensure_thumbnail(key, ctype):
            continue
        url = files.thumbnail_url(str(row["name"]), key, ctype)
        await grunt.db.set_value("File", row["name"], {"thumbnail_url": url})
        made += 1
    return made


@whitelist(allow_guest=True)
async def get_content(
    file_id: str,
    exp: int | None = None,
    sig: str | None = None,
    thumb: bool = False,
    request: Request | None = None,
) -> Response:
    """Whitelisted method: Stream file content from storage (``thumb`` - its preview).

    A private file needs either a valid signature (``exp`` + ``sig``, appended
    to every file URL the API hands out) or a user allowed to read it.
    """
    from grunt.storage.signing import verify

    # Use grunt.db directly to avoid permission checks that require an active user.
    doc = await grunt.db.get_values(
        "File",
        file_id,
        [
            "name",
            "owner",
            "content_hash",
            "content_type",
            "file_name",
            "is_public",
            "attached_to_doctype",
            "attached_to_id",
        ],
    )
    if not doc:
        raise HTTPException(404, _("File not found"))

    # A private file needs an authenticated user who may read it - which, for
    # an attachment, means reading the document it is attached to.
    if not doc.get("is_public") and not verify(file_id, exp, sig):
        user = _user_ctx.get()
        if user is None:
            raise HTTPException(401, _("Authentication required to access this file"))
        from grunt.permissions.rbac import permission_checker

        meta = await grunt.get_meta("File")
        if meta is None or not await permission_checker.check(user, meta, "read", doc):
            raise HTTPException(403, _("No access to the file"))

    key = doc.get("content_hash") or ""
    storage = get_storage_backend()
    # A blob never changes (it is named by its hash) - let the browser keep
    # it and revalidate by ETag. "private": access is per user.
    etag = f'"{key}-thumb"' if thumb else f'"{key}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=86400"}
    try:
        path = storage.thumbnail_path(key) if thumb else storage.path(key)
    except FileNotFoundError:
        path = None
    if path is None or not path.exists():
        raise HTTPException(404, _("File not found on storage"))
    if isinstance(request, Request) and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    if thumb:
        return FileResponse(path, media_type=THUMB_MIMETYPE, headers=headers)
    # Streamed from disk, with Range support (video, large PDFs).
    return FileResponse(
        path,
        media_type=doc.get("content_type"),
        filename=doc.get("file_name") or "file",
        content_disposition_type="attachment",
        headers=headers,
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
                "thumbnail_url": r.thumbnail_url,
                "filename": r.file_name,
                "content_type": r.content_type,
                "content_hash": r.content_hash,
                "size_bytes": r.file_size,
                "created_at": str(r.created_at) if r.created_at else None,
                "uploaded_by": r.uploaded_by,
                "attached_to_doctype": r.attached_to_doctype,
                "attached_to_id": r.attached_to_id,
            }
            for r in records
        ],
        "total": total,
    }


@whitelist()
async def remove(file_id: str) -> bool:
    """Whitelisted method: Delete a file (permission-checked by delete_doc).

    The blob stays until the storage garbage collector finds nothing - no
    other File row, no trashed snapshot - pointing at it (grunt.storage.gc).
    """
    await grunt.delete_doc("File", file_id)
    return True
