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
    attached_to_doctype: str | None
    attached_to_id: str | None

    async def before_delete(self) -> None:
        """Delete the physical file before the DB row.

        Not best-effort: if the storage backend fails, the File document must
        not be deleted either — otherwise the row disappears while the
        physical file silently survives as an orphan with no record pointing
        to it. Letting the exception propagate aborts the whole delete
        pipeline (see ``DocumentWriteMixin.delete_document``).

        Storage de-duplication (see ``dedupe_storage``) lets several File rows
        share one blob, so only drop the physical file when this is the last
        row pointing at that path.
        """
        if not self.path:
            return
        others = await File.objects.filter(path=self.path, name__ne=self.name).count()
        if others == 0:
            storage = get_storage_backend()
            await storage.delete(self.path)


@whitelist()
async def upload(
    file: UploadFile,
    attached_to_doctype: str | None = None,
    attached_to_id: str | None = None,
    is_public: bool | None = None,
) -> dict[str, Any]:
    """Whitelisted method: Upload a file and create a File document.

    An attachment (``attached_to_*`` set) is private unless ``is_public`` is
    passed explicitly — readable only with its document, via a signed URL (see
    :mod:`grunt.storage.signing`). A free-standing library file stays public.
    """
    if is_public is None:
        is_public = not attached_to_doctype
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    try:
        content = await file.read()
    finally:
        await file.close()
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
        is_public=is_public,
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
async def get_content(file_id: str, exp: int | None = None, sig: str | None = None) -> Response:
    """Whitelisted method: Fetch file content from storage.

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
            "path",
            "content_type",
            "file_name",
            "is_public",
            "attached_to_doctype",
            "attached_to_id",
        ],
    )
    if not doc:
        raise HTTPException(404, "File not found")

    # A private file needs an authenticated user who may read it — which, for
    # an attachment, means reading the document it is attached to.
    if not doc.get("is_public") and not verify(file_id, exp, sig):
        user = _user_ctx.get()
        if user is None:
            raise HTTPException(401, "Authentication required to access this file")
        from grunt.permissions.rbac import permission_checker

        meta = await grunt.get_meta("File")
        if meta is None or not await permission_checker.check(user, meta, "read", doc):
            raise HTTPException(403, "Немає доступу до файлу")

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


@whitelist(roles=["System Manager"])
async def dedupe_storage(backfill: bool = True) -> dict[str, Any]:
    """Admin op: make byte-identical File rows share one stored blob.

    1. (``backfill``) fill ``content_hash`` for rows missing it, reading the blob.
    2. Group rows by (content_hash, file_size); in each group repoint every
       row's ``path`` to the oldest row's path and delete the blobs that no
       row references any more.

    Rows, ids, URLs and per-row metadata are untouched — only disk is reclaimed.
    ``File.before_delete`` is ref-counted, so a later delete of any shared row
    keeps the blob until the last row goes.
    """
    storage = get_storage_backend()

    rows: list[File] = []
    page = 1
    while True:
        batch = await File.objects.order_by("created_at").limit(500).page(page).all()
        if not batch:
            break
        rows.extend(batch)
        page += 1

    backfilled = 0
    if backfill:
        for r in rows:
            if r.content_hash or not r.path:
                continue
            try:
                data = await storage.get(r.path)
            except Exception:
                continue
            r.content_hash = hashlib.sha256(data).hexdigest()
            await grunt.save_doc("File", str(r.name), {"content_hash": r.content_hash})
            backfilled += 1

    groups: dict[tuple[str, int], list[File]] = {}
    for r in rows:
        if r.content_hash and r.path:
            groups.setdefault((r.content_hash, r.file_size), []).append(r)

    merged_rows = freed_blobs = freed_bytes = 0
    for (_, size), group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: str(r.created_at or ""))
        canonical = group[0]
        stale_paths: set[str] = set()
        for r in group[1:]:
            if r.path == canonical.path:
                continue
            stale_paths.add(r.path)
            await grunt.save_doc("File", str(r.name), {"path": canonical.path})
            r.path = canonical.path
            merged_rows += 1
        for stale in stale_paths:
            if await File.objects.filter(path=stale).count() == 0:
                try:
                    await storage.delete(stale)
                except Exception:
                    continue
                freed_blobs += 1
                freed_bytes += size

    return {
        "backfilled_hashes": backfilled,
        "duplicate_groups": sum(1 for g in groups.values() if len(g) > 1),
        "merged_rows": merged_rows,
        "freed_blobs": freed_blobs,
        "freed_bytes": freed_bytes,
    }
