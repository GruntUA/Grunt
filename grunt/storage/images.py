"""Compressing images stored before compression was on (``grunt files compress``,
System Settings → Files). How an image is compressed: grunt/storage/optimize.py.
"""

from grunt.api.context import whitelist
from grunt.api.results import Queued
from grunt.db.api import GruntDB
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import require_session, user_email
from grunt.storage import files, optimize
from grunt.storage.backends import get_storage_backend
from grunt.storage.cloud.files import read_blob
from grunt.storage.optimize import OPTIMIZABLE, optimize_image, renamed
from grunt.tasks.broker import by_name
lazy from grunt.progress import Progress

_db = GruntDB()  # stateless: reads through the context's session


async def compress_existing(
    *, apply: bool = False, limit: int | None = None, progress: Progress | None = None
) -> dict:
    """Compress images stored before compression was on (``grunt files compress``).

    Files already compressed (``File.is_compressed``) are skipped. Each
    distinct blob is re-encoded once and every ``File`` row over it is
    moved to the new one (size, type, extension, preview); the old blob is
    left to the garbage collector. A dry run (``apply=False``) only measures.
    Returns ``{"blobs", "files", "before", "after"}`` - what was (or would be)
    compressed, sizes in bytes. *progress* counts the blobs (and is where a
    cancel lands - between two blobs, so what's done stays done).
    """

    report = {"blobs": 0, "files": 0, "before": 0, "after": 0}
    opts = await optimize.image_options()
    if opts is None:
        return report
    rows = await _db.get_all(
        "File",
        filters={"content_type__in": sorted(OPTIMIZABLE)},
        fields=["name", "file_name", "content_hash", "content_type", "file_size", "is_compressed"],
        limit=None,
    )
    by_blob: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if row["content_hash"] and not row["is_compressed"]:
            by_blob.setdefault((row["content_hash"], row["content_type"]), []).append(row)

    # Minutes of image work ahead: don't hold the read transaction (on SQLite
    # it is the write lock) all along.
    await require_session().commit()
    blobs = list(by_blob.items())[:limit]
    if progress:
        progress.set(total=len(blobs))

    storage = get_storage_backend()
    for (key, content_type), group in blobs:
        if progress:
            progress.advance(1)
        try:
            content = await read_blob(key)
        except FileNotFoundError:
            continue
        optimized = await optimize_image(content, content_type, opts)
        if optimized is None:
            continue
        report["blobs"] += 1
        report["files"] += len(group)
        report["before"] += len(content)
        report["after"] += len(optimized.content)
        if not apply:
            continue
        new_key, new_size = await storage.put(optimized.content)
        await files.ensure_thumbnail(new_key, optimized.content_type)
        # Re-read: while the image was encoded, its files may have been
        # renamed, deleted or joined by new ones.
        group = await _db.get_all(
            "File",
            filters={"content_hash": key, "content_type": content_type},
            fields=["name", "file_name", "file_size", "is_compressed"],
            limit=None,
        )
        for row in group:
            if row["is_compressed"]:
                continue
            file_id = str(row["name"])
            await _db.set_value(
                "File",
                file_id,
                {
                    "content_hash": new_key,
                    "file_size": new_size,
                    "content_type": optimized.content_type,
                    "file_name": renamed(row["file_name"], optimized.content_type),
                    "storage_remote": None,  # the new blob is local
                    "is_compressed": True,
                    "original_size": row["file_size"],
                    "thumbnail_url": files.thumbnail_url(file_id, new_key, optimized.content_type),
                },
            )
        await require_session().commit()
    return report


@whitelist(roles=["System Manager"])
async def start_compression() -> Queued:
    """Queue :func:`compress_existing` for the whole site (System Settings →
    Files); whoever started it follows it in the task panel."""

    if await optimize.image_options() is None:
        throw(_("Image compression is turned off in System Settings"))
    await by_name("grunt.storage.tasks:compress_images").kiq(user=user_email())
    return {"queued": True}
