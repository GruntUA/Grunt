"""Storing files - the one way content becomes a ``File`` row.

Everything that keeps bytes for later (uploads, web forms, mail attachments,
exports, generated documents) goes through :func:`store`: MIME allowlist,
size limit, content-addressed blob (grunt.storage.backends), ``File`` row,
its URL and preview. Readers use :func:`read` by ``File`` id.
"""

from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, BinaryIO

import grunt
from grunt import _, log
from grunt.config import settings
from grunt.storage.backends import get_storage_backend
from grunt.storage.images import OPTIMIZABLE, optimize_image, renamed
from grunt.storage.thumbnails import THUMB_WIDTH, WEB_WIDTHS, can_thumbnail, make_thumbnail
lazy from grunt.local import _user_ctx
lazy from grunt.site.settings import get_setting
lazy from grunt.storage.cloud.files import read_blob

CONTENT_URL = "/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id={}"

# MIME type allowlist
ALLOWED_MIME_TYPES: set[str] = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "application/json",
    "application/zip",
}


class FileTypeNotAllowedError(ValueError):
    """The content type is not in ALLOWED_MIME_TYPES."""


def validate_mime_type(content_type: str) -> None:
    """Raise FileTypeNotAllowedError if the MIME type is not in the allowlist."""
    base_type = content_type.split(";")[0].strip().lower()
    if base_type not in ALLOWED_MIME_TYPES:
        raise FileTypeNotAllowedError(
            _("File type “%(type)s” is not allowed") % {"type": base_type}
        )


def parse_file_types(value: str | None) -> set[str]:
    """``".exe, msi application/x-msdownload"`` -> ``{".exe", ".msi", "application/x-msdownload"}``.

    Entries are split by commas, semicolons or whitespace (one per line is
    fine). One with a ``/`` is a MIME type, anything else - a file extension.
    """
    types: set[str] = set()
    for raw in (value or "").replace(",", "\n").replace(";", "\n").split():
        item = raw.strip().lower()
        if item:
            types.add(item if "/" in item or item.startswith(".") else f".{item}")
    return types


async def validate_file_type(content_type: str, filename: str | None = None) -> None:
    """Like :func:`validate_mime_type`, plus the site's own extra types.

    ``SystemSettings.extra_file_types`` lists extensions (``.exe``) or MIME
    types an admin allows on top of ALLOWED_MIME_TYPES. An extension is
    matched by the file name: browsers send an ``.exe`` as
    ``application/x-msdownload``, ``application/x-msdos-program`` or a bare
    ``application/octet-stream``. Such files are always served as a download
    (``Content-Disposition: attachment``), never rendered inline.
    """
    base_type = content_type.split(";")[0].strip().lower()
    if base_type in ALLOWED_MIME_TYPES:
        return
    extra = parse_file_types(await get_setting("extra_file_types", ""))
    suffix = PurePath(filename).suffix.lower() if filename else ""
    if base_type not in extra and not (suffix and suffix in extra):
        raise FileTypeNotAllowedError(
            _("File type “%(type)s” is not allowed") % {"type": suffix or base_type}
        )


def upload_limit() -> int:
    """Size limit for user uploads, in bytes (``settings.max_upload_size_mb``)."""
    return settings.max_upload_size_mb * 1024 * 1024


def thumbnail_url(file_id: str, key: str, content_type: str | None) -> str | None:
    """Preview URL of a file, or None when it has none (yet)."""
    if content_type == "image/svg+xml":
        return CONTENT_URL.format(file_id)  # the browser draws the file itself
    if get_storage_backend().thumbnail_path(key).exists():
        return CONTENT_URL.format(file_id) + "&thumb=1"
    return None


async def ensure_thumbnail(key: str, content_type: str | None, width: int | None = None) -> bool:
    """Make the blob's preview (*width* px wide - one of ``WEB_WIDTHS``; the
    standard one by default) unless it exists; False when it can't have one.

    Previews are keyed by content, so every File with the same bytes shares one.
    """
    if not can_thumbnail(content_type):
        return False
    width = None if width == THUMB_WIDTH else width
    storage = get_storage_backend()
    if storage.thumbnail_path(key, width).exists():
        return True

    try:
        content = await read_blob(key)  # may be fetched from cloud storage
    except FileNotFoundError:
        return False
    thumb = await make_thumbnail(content, content_type, width or THUMB_WIDTH)
    if thumb is None:
        return False
    await storage.put_thumbnail(key, thumb, width)
    return True


def _content_url(url: str | None) -> bool:
    return bool(url) and str(url).startswith(CONTENT_URL.format(""))


def sized_url(url: str | None, width: int) -> str:
    """*url* of a stored image as its *width* px WebP preview (a page's ``<img src>``).

    Anything else (a static asset, an external link, an SVG) is returned as is.
    """
    if not _content_url(url) or width not in WEB_WIDTHS:
        return url or ""
    return f"{url}&w={width}"


def image_srcset(url: str | None) -> str:
    """``srcset`` of every web preview width for *url*; empty when it has none."""
    if not _content_url(url):
        return ""
    return ", ".join(f"{url}&w={w} {w}w" for w in WEB_WIDTHS)


async def create_file(
    key: str,
    size: int,
    filename: str,
    content_type: str,
    *,
    attached_to_doctype: str | None = None,
    attached_to_id: str | None = None,
    folder: str | None = None,
    is_public: bool = False,
    uploaded_by: str | None = None,
    original_size: int | None = None,
) -> dict[str, Any]:
    """Create the ``File`` row for an already stored blob; return it.

    *original_size* - the blob is a compressed copy (:func:`compress_stored`)
    of an upload that many bytes long.
    """
    if uploaded_by is None:
        uploaded_by = getattr(_user_ctx.get(), "email", None)
    doc = await grunt.new_doc(
        "File",
        {
            "file_name": filename,
            "file_url": "",  # needs the generated name - set below
            "content_hash": key,
            "content_type": content_type,
            "file_size": size,
            "uploaded_by": uploaded_by,
            "is_public": is_public,
            "attached_to_doctype": attached_to_doctype or None,
            "attached_to_id": attached_to_id or None,
            "folder": folder or None,
            "is_compressed": original_size is not None,
            "original_size": original_size,
        },
    )
    file_id = str(doc["name"])
    await ensure_thumbnail(key, content_type)
    values = {
        "file_url": CONTENT_URL.format(file_id),
        "thumbnail_url": thumbnail_url(file_id, key, content_type),
    }
    await grunt.db.set_value("File", file_id, values)
    doc.update(values)
    return doc


@dataclass(frozen=True)
class StoredBlob:
    """A stored blob about to get its ``File`` row."""

    key: str
    size: int
    filename: str
    content_type: str
    original_size: int | None = None  # set when this is a compressed copy


async def compress_stored(key: str, size: int, filename: str, content_type: str) -> StoredBlob:
    """Swap a stored image for its compressed copy (grunt.storage.images).

    Returns the new blob - its extension following a format change, and
    ``original_size`` set - or the given one when the image stays as it is.
    The original blob is left to the garbage collector.
    """
    blob = StoredBlob(key, size, filename, content_type)
    if content_type not in OPTIMIZABLE:
        return blob
    storage = get_storage_backend()
    optimized = await optimize_image(await storage.get(key), content_type)
    if optimized is None:
        return blob
    new_key, new_size = await storage.put(optimized.content)
    log.info("storage.image_compressed", before=size, after=new_size, type=optimized.content_type)
    return StoredBlob(
        new_key,
        new_size,
        renamed(filename, optimized.content_type),
        optimized.content_type,
        original_size=size,
    )


async def store(
    content: bytes | BinaryIO,
    filename: str,
    content_type: str | None = None,
    *,
    attached_to_doctype: str | None = None,
    attached_to_id: str | None = None,
    folder: str | None = None,
    is_public: bool = False,
    uploaded_by: str | None = None,
    max_bytes: int | None = None,
    compress: bool = True,
) -> dict[str, Any]:
    """Store *content* (bytes or a binary stream) as a new ``File``; return the row.

    Raises FileTypeNotAllowedError / FileTooLargeError (both ValueError) before anything
    is written. Private by default - pass ``is_public`` for website content.
    Photos are compressed per the site's settings (grunt.storage.images) -
    pass ``compress=False`` to keep the exact bytes.
    """
    content_type = content_type or "application/octet-stream"
    await validate_file_type(content_type, filename)
    key, size = await get_storage_backend().put(content, max_bytes=max_bytes)
    blob = (
        await compress_stored(key, size, filename, content_type)
        if compress
        else StoredBlob(key, size, filename, content_type)
    )
    return await create_file(
        blob.key,
        blob.size,
        blob.filename,
        blob.content_type,
        attached_to_doctype=attached_to_doctype,
        attached_to_id=attached_to_id,
        folder=folder,
        is_public=is_public,
        uploaded_by=uploaded_by,
        original_size=blob.original_size,
    )


async def read(file_id: str) -> bytes:
    """Bytes of the ``File`` *file_id* (no permission check - callers gate access)."""
    key = await grunt.db.get_value("File", file_id, "content_hash")
    if not key:
        raise FileNotFoundError(f"File not found: {file_id}")

    return await read_blob(key)
