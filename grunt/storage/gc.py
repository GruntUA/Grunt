"""Storage garbage collection and integrity check.

A ``File`` row going away never touches disk (other rows may share its blob,
and the trash may restore it). Instead :func:`collect_garbage` drops blobs no
``File`` row - nor a ``File`` snapshot still in the trash (DeletedDocument) -
refers to, once they are older than a grace period: a blob is written before
its row exists, and a re-upload of known content freshens the blob's mtime,
so a collection racing an upload leaves it alone.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

import grunt
from grunt import log
from grunt.storage.backends import CHUNK_SIZE, get_storage_backend

GRACE_SECONDS = 3600


async def referenced_keys() -> set[str]:
    """Content hashes still needed: live ``File`` rows + unrestored trashed ones."""
    keys = set(
        await grunt.db.get_all(
            "File", filters={"content_hash__isnull": False}, pluck="content_hash", limit=None
        )
    )
    trashed = await grunt.db.get_all(
        "DeletedDocument",
        filters={"deleted_doctype": "File", "restored": 0},
        pluck="data",
        limit=None,
    )
    for data in trashed:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                continue
        if isinstance(data, dict) and data.get("content_hash"):
            keys.add(data["content_hash"])
    return keys


async def collect_garbage(grace_seconds: int = GRACE_SECONDS) -> dict[str, Any]:
    """Delete unreferenced blobs (and their previews) and abandoned uploads.

    Call it with the site's session bound; the transaction is closed before
    the disk work so a worker's ``BEGIN IMMEDIATE`` doesn't hold the write lock.
    """
    storage = get_storage_backend()
    cutoff = time.time() - grace_seconds
    candidates = await asyncio.to_thread(
        lambda: {key for key, mtime in storage.iter_keys() if mtime < cutoff}
    )
    keep = await referenced_keys()
    await grunt.get_session().commit()

    freed = freed_bytes = 0
    for key in candidates - keep:
        path = storage.path(key)
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if stat.st_mtime >= cutoff:  # re-uploaded meanwhile
            continue
        await storage.delete(key)
        freed += 1
        freed_bytes += stat.st_size
    tmp_removed = await asyncio.to_thread(storage.sweep_tmp, cutoff)

    report = {"freed_blobs": freed, "freed_bytes": freed_bytes, "tmp_removed": tmp_removed}
    log.info("storage.gc", **report)
    return report


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


async def verify(rehash: bool = False) -> dict[str, list[str]]:
    """Find ``File`` rows whose blob is missing, unreferenced blobs, and - with
    *rehash* - blobs whose bytes no longer match their name (disk corruption).
    """
    storage = get_storage_backend()
    rows = await grunt.db.get_all("File", fields=["name", "content_hash"], limit=None)
    await grunt.get_session().commit()

    missing = [
        str(r["name"])
        for r in rows
        if not r["content_hash"] or not storage.path(r["content_hash"]).exists()
    ]
    on_disk = await asyncio.to_thread(lambda: [key for key, _ in storage.iter_keys()])
    referenced = {r["content_hash"] for r in rows if r["content_hash"]}
    unreferenced = sorted(set(on_disk) - referenced)
    corrupt: list[str] = []
    if rehash:
        for key in on_disk:
            if await asyncio.to_thread(_sha256, storage.path(key)) != key:
                corrupt.append(key)
    return {"missing": missing, "unreferenced": unreferenced, "corrupt": corrupt}
