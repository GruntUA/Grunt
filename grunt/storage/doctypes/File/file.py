from typing import Any

import httpx2
from fastapi import HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, or_, select

import grunt
from grunt import _
from grunt.api.context import whitelist
from grunt.document.base import Document
from grunt.local import _user_ctx
from grunt.storage import files, quota
from grunt.storage.backends import FileTooLargeError, get_storage_backend
from grunt.storage.cloud.files import blob_path
from grunt.storage.signing import verify
from grunt.storage.thumbnails import THUMB_MIMETYPE, THUMB_WIDTH, WEB_WIDTHS, can_thumbnail
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.permissions.rbac import permission_checker
lazy from grunt.storage.doctypes.FileFolder.file_folder import require_folder_write
lazy from grunt.storage.references import file_ids_in
lazy from grunt.storage.remote import RemoteFileError, fetch_file


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
    storage_remote: str | None
    is_compressed: bool
    original_size: int | None

    _prev_folder: str | None = None

    async def before_save(self) -> None:
        """Filing into a folder needs write access to it and room in its space.

        Moving keeps ``is_public``: a file is published by the website content
        that links it (see :mod:`grunt.storage.references`), not by its folder,
        so tidying an image into another folder must not break a published page.
        Approved by the site owner (maks4a@gmail.com), 2026-10-09."""
        if not self.folder:
            return
        if self.id and self._prev_folder is None:
            self._prev_folder = await grunt.db.get_value("File", self.id, "folder") or ""
        if self.folder == self._prev_folder:
            return

        folder = await grunt.db.get_value("FileFolder", self.folder, "*")
        if folder is None:
            grunt.throw(_("Folder “%(folder)s” not found") % {"folder": self.folder})
        await require_folder_write(folder)
        prev_space = (
            await grunt.db.get_value("FileFolder", self._prev_folder, "space_user")
            if self._prev_folder
            else None
        )
        if folder["space_user"] != prev_space:
            await quota.ensure_room(folder["space_user"], self.file_size or 0)

    async def before_delete(self) -> None:
        """A file that a document still uses can't be deleted.

        Used means attached to an existing document or linked from any
        document's field (an image in an article's text, a cover, ...):
        deleting it would break that document. Approved by the site owner
        (maks4a@gmail.com), 2026-10-13."""
        if (
            self.attached_to_doctype
            and self.attached_to_id
            and await grunt.db.exists(self.attached_to_doctype, self.attached_to_id)
        ):
            grunt.throw(
                _("The file can't be deleted: it is attached to %(doctype)s “%(doc)s”")
                % {"doctype": self.attached_to_doctype, "doc": self.attached_to_id}
            )
        if used_in := await _documents_using(str(self.id)):
            grunt.throw(
                _("The file can't be deleted: it is used in %(doctype)s “%(doc)s”")
                % {"doctype": used_in[0], "doc": used_in[1]}
            )


# Fields that may hold a file's URL: file fields and free text / markup.
_REF_FIELD_TYPES = frozenset(
    {"Attach", "Image", "RichText", "HTMLEditor", "Text", "LongText", "Code", "JSON", "Data"}
)
# History and logs only remember a link - they don't keep a file in use.
_NOT_USERS = frozenset(
    {
        "File",
        "DocVersion",
        "DeletedDocument",
        "ActivityLog",
        "ViewLog",
        "AssignmentLog",
        "ErrorLog",
        "EmailQueue",
        "Notification",
        "ScheduledJobLog",
        "WebhookLog",
        "IncomingWebhookLog",
    }
)


async def _documents_using(file_id: str) -> tuple[str, str] | None:
    """(DocType, id) of some document whose field links *file_id*, or ``None``.

    A child-table row is reported as its parent document.
    """

    session = grunt.get_session()
    pattern = f"%file_id={file_id}%"
    for dt in await doctype_registry.list_all():
        if dt.name in _NOT_USERS or dt.is_virtual:
            continue
        meta = Meta(dt)
        table = meta.table
        columns = [
            table.c[f.fieldname]
            for f in meta.fields
            if f.fieldtype in _REF_FIELD_TYPES and f.fieldname in table.c
        ]
        if not columns:
            continue
        child = bool(dt.is_child)
        extra = [table.c.parent_doctype, table.c.parent_name] if child else []
        rows = await session.execute(
            select(table.c.name, *extra, *columns).where(
                or_(*(cast(c, String).like(pattern) for c in columns))
            )
        )
        for row in rows:
            values = row[1 + len(extra) :]
            # LIKE also matches a longer id that starts with this one.
            if not any(file_id in file_ids_in(str(v)) for v in values if v is not None):
                continue
            return (str(row[1]), str(row[2])) if child else (dt.name, str(row[0]))
    return None


@whitelist()
async def upload(
    file: UploadFile,
    attached_to_doctype: str | None = None,
    attached_to_id: str | None = None,
    is_public: bool | None = None,
    folder: str | None = None,
) -> dict[str, Any]:
    """Whitelisted method: Upload a file and create a File document.

    A file is private - readable via a signed URL (see
    :mod:`grunt.storage.signing`) by whoever may read it - unless ``is_public``
    is passed explicitly or the attachment's DocType sets
    ``public_attachments``. ``folder`` files it into a personal space
    (FileFolder) - that needs write access to the folder and room in its quota.
    """
    if is_public is None:
        meta = await grunt.get_meta(attached_to_doctype) if attached_to_doctype else None
        is_public = bool(meta and meta.public_attachments)
    if not file.filename:
        raise HTTPException(400, _("No filename provided"))
    if folder:
        # Fail before streaming the body; File.before_save re-checks with the size.

        row = await grunt.db.get_value("FileFolder", folder, "*")
        if row is None:
            raise HTTPException(404, _("Folder “%(folder)s” not found") % {"folder": folder})
        await require_folder_write(row)

    content_type = file.content_type or "application/octet-stream"
    try:
        await files.validate_file_type(content_type, file.filename)
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
    blob = await files.compress_stored(key, size, file.filename, content_type)

    # The blob is stored once whatever happens; this only decides whether a
    # re-upload of the same name + bytes by the same user for the same target
    # reuses its File row instead of listing a second one. A different name -
    # or the same bytes for a *different* document - gets its own row.
    existing = await File.objects.filter(
        file_name=blob.filename,
        content_hash=blob.key,
        uploaded_by=grunt.get_user().email,
        attached_to_doctype=attached_to_doctype or None,
        attached_to_id=attached_to_id or None,
        folder=folder or None,
    ).first()
    if existing is not None:
        return _upload_payload(existing.as_dict(), deduped=True)

    doc = await files.create_file(
        blob.key,
        blob.size,
        blob.filename,
        blob.content_type,
        attached_to_doctype=attached_to_doctype,
        attached_to_id=attached_to_id,
        folder=folder,
        is_public=is_public,
        original_size=blob.original_size,
    )
    return _upload_payload(doc, deduped=False)


@whitelist()
async def upload_from_url(url: str, folder: str | None = None) -> dict[str, Any]:
    """Whitelisted method: download a file from the internet into *folder*
    (see :mod:`grunt.storage.remote` for what links are allowed)."""

    if folder:
        row = await grunt.db.get_value("FileFolder", folder, "*")
        if row is None:
            raise HTTPException(404, _("Folder “%(folder)s” not found") % {"folder": folder})
        await require_folder_write(row)
    try:
        doc = await fetch_file(url.strip(), folder=folder or None)
    except RemoteFileError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx2.HTTPError as exc:
        raise HTTPException(
            422, _("Could not download the file: %(error)s") % {"error": exc}
        ) from exc
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
        "folder": doc.get("folder"),
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
    w: int | None = None,
    request: Request | None = None,
) -> Response:
    """Whitelisted method: Stream file content from storage (``thumb`` - its preview,
    ``w`` - a preview that wide, one of ``WEB_WIDTHS``, for ``srcset`` on pages).

    A private file needs either a valid signature (``exp`` + ``sig``, appended
    to every file URL the API hands out) or a user allowed to read it.
    """
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

        meta = await grunt.get_meta("File")
        if meta is None or not await permission_checker.check(user, meta, "read", doc):
            raise HTTPException(403, _("No access to the file"))

    key = doc.get("content_hash") or ""
    storage = get_storage_backend()
    # A sized preview for a page's srcset, made on first request. A width
    # outside WEB_WIDTHS or a file without previews (SVG) gets the original.
    width = None
    if w in WEB_WIDTHS and await files.ensure_thumbnail(key, doc.get("content_type"), w):
        width, thumb = (None if w == THUMB_WIDTH else w), True
    # A blob never changes (it is named by its hash) - let the browser keep
    # it and revalidate by ETag. A public file (website images) may sit in a
    # shared cache (CDN); anything else is per user.
    etag = f'"{key}-{width or "thumb"}"' if thumb else f'"{key}"'
    scope = "public" if doc.get("is_public") else "private"
    headers = {"ETag": etag, "Cache-Control": f"{scope}, max-age=86400"}
    if isinstance(request, Request) and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    try:
        # The original may be in cloud storage - fetched into the local cache.
        path = storage.thumbnail_path(key, width) if thumb else await blob_path(key)
    except FileNotFoundError:
        path = None
    if path is None or not path.exists():
        raise HTTPException(404, _("File not found on storage"))
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
    # ``records`` is row-level filtered (grunt.get_all), so the total must be
    # too - a raw count would reveal how many files the user may NOT see.
    total = await grunt.count("File", filters=all_filters or None, respect_permissions=True)

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
