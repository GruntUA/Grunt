"""Old files moved off the server disk into cloud storage.

The unit is a blob (``uploads/blobs/ab/cd/<sha256>``), not a ``File`` row:
rows sharing content share the blob, so a blob moves only when every row
pointing at it fits the remote's policy (age, size, public or not, DocType).
It goes to ``<root>/files/<site>/ab/cd/<sha256>``, the rows get
``storage_remote``, and the local copy is deleted - previews stay, so lists
and galleries never touch the cloud.

Reading (:func:`blob_path`) is local first: the blob, else a copy in
``uploads/cache/``, else it is downloaded into the cache (and checked against
its hash). The nightly garbage collection trims the cache to the remote's
size, oldest-used first, and deletes remote blobs nothing refers to any more.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import grunt
from grunt import _, log
from grunt.site.manager import site_manager
from grunt.storage.backends import CHUNK_SIZE, get_storage_backend
from grunt.storage.cloud import RemoteError, files_remote, load_remote, record_status
from grunt.storage.cloud.rclone import Rclone

if TYPE_CHECKING:
    from grunt.progress import Progress
    from grunt.storage.backends import LocalStorageBackend

# One night moves at most this many blobs; the rest go the next night.
MAX_BLOBS_PER_RUN = 5000
_CHUNK = 500  # keys per IN (...) query
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def remote_dir() -> str:
    return f"files/{site_manager.get_active_site()}"


def relative(key: str) -> str:
    return f"{key[:2]}/{key[2:4]}/{key}"


def _storage() -> LocalStorageBackend:
    return get_storage_backend()  # type: ignore[return-value]


def cache_root() -> Path:
    return _storage().root / "cache"


def cache_path(key: str) -> Path:
    _storage().path(key)  # validates the key
    return cache_root() / relative(key)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _chunks(items: list[str]):
    for i in range(0, len(items), _CHUNK):
        yield items[i : i + _CHUNK]


# Reading


async def blob_path(key: str) -> Path:
    """Local path of the blob *key*, fetched from cloud storage when needed.

    FileNotFoundError when it is nowhere.
    """
    path = _storage().path(key)
    if path.exists():
        return path
    cached = cache_path(key)
    if cached.exists():
        os.utime(cached)  # last used - the cache is trimmed oldest-used first
        return cached
    async with _locks[key]:  # one download per blob, however many readers wait
        if cached.exists():
            return cached
        remote_name = (
            await grunt.db.get_all(
                "File",
                filters={"content_hash": key, "storage_remote__isnull": False},
                pluck="storage_remote",
                limit=1,
            )
            or [None]
        )[0]
        if not remote_name:
            raise FileNotFoundError(f"File not found: {key}")
        await _download(await load_remote(remote_name), key, cached)
    _locks.pop(key, None)
    return cached


async def _download(remote: dict[str, Any], key: str, dest: Path) -> None:
    tmp_dir = _storage().root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / uuid.uuid4().hex
    try:
        async with Rclone(remote) as rc:
            await rc.get_file(f"{remote_dir()}/{relative(key)}", tmp)
        if await asyncio.to_thread(_sha256, tmp) != key:
            raise RemoteError(_("The file from the storage is damaged: %(key)s") % {"key": key})
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, dest)
    except RemoteError as exc:
        log.warning("cloud.fetch_failed", key=key, remote=remote["name"], error=str(exc))
        raise FileNotFoundError(f"File not available from storage: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)
    log.info("cloud.fetched", key=key, remote=remote["name"])


async def read_blob(key: str) -> bytes:
    return await asyncio.to_thread((await blob_path(key)).read_bytes)


# Moving files out


def _doctypes(remote: dict[str, Any]) -> list[str]:
    return [
        line.strip() for line in (remote.get("offload_doctypes") or "").splitlines() if line.strip()
    ]


def _qualifies(row: dict[str, Any], remote: dict[str, Any], cutoff: datetime) -> bool:
    if row.get("storage_remote"):
        return True  # already out - doesn't hold the blob back
    created = row.get("created_at")
    if created is None or created >= cutoff:
        return False
    if (row.get("file_size") or 0) < int(remote.get("offload_min_size_kb") or 0) * 1024:
        return False
    if row.get("is_public") and not remote.get("offload_public"):
        return False
    doctypes = _doctypes(remote)
    return not doctypes or row.get("attached_to_doctype") in doctypes


async def offload_candidates(remote: dict[str, Any], limit: int = MAX_BLOBS_PER_RUN) -> list[str]:
    """Blobs on this disk whose every ``File`` row fits *remote*'s policy."""
    cutoff = datetime.now(UTC) - timedelta(days=int(remote.get("offload_after_days") or 0))
    filters: dict[str, Any] = {"storage_remote__isnull": True, "created_at__lt": cutoff}
    if remote.get("offload_min_size_kb"):
        filters["file_size__gte"] = int(remote["offload_min_size_kb"]) * 1024
    if not remote.get("offload_public"):
        filters["is_public"] = 0
    if doctypes := _doctypes(remote):
        filters["attached_to_doctype__in"] = doctypes
    keys = sorted(
        set(await grunt.db.get_all("File", filters=filters, pluck="content_hash", limit=None))
    )
    storage = _storage()
    chosen: list[str] = []
    fields = [
        "content_hash",
        "storage_remote",
        "created_at",
        "file_size",
        "is_public",
        "attached_to_doctype",
    ]
    for chunk in _chunks(keys):
        rows = await grunt.db.get_all(
            "File", filters={"content_hash__in": chunk}, fields=fields, limit=None
        )
        by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_key[row["content_hash"]].append(row)
        for key in chunk:
            if (
                all(_qualifies(r, remote, cutoff) for r in by_key[key])
                and storage.path(key).exists()
            ):
                chosen.append(key)
                if len(chosen) >= limit:
                    return chosen
    return chosen


async def offload(remote: dict[str, Any], progress: Progress | None = None) -> dict[str, int]:
    """Move the blobs fitting *remote*'s policy into it; ``{"files", "bytes"}``.

    Order matters for a crash at any point: upload, then point the rows at the
    remote (commit), then delete the local copy - a blob is always readable.
    """
    session = grunt.get_session()
    keys = await offload_candidates(remote)
    await session.commit()
    if not keys:
        await _update_stats(remote)
        return {"files": 0, "bytes": 0}
    storage = _storage()
    sizes = {key: storage.path(key).stat().st_size for key in keys}
    if progress is not None:
        progress.set(
            stage=_("Moving %(n)s files to the storage") % {"n": len(keys)},
            total=sum(sizes.values()),
        )
    async with Rclone(remote) as rc:
        await rc.copy_files(
            storage.root / "blobs", [relative(k) for k in keys], remote_dir(), progress=progress
        )
    for chunk in _chunks(keys):
        await grunt.db.bulk_update(
            "File",
            {"content_hash__in": chunk, "storage_remote__isnull": True},
            {"storage_remote": remote["name"]},
        )
    await session.commit()
    for key in keys:
        storage.path(key).unlink(missing_ok=True)
    await _update_stats(remote)
    report = {"files": len(keys), "bytes": sum(sizes.values())}
    log.info("cloud.offloaded", remote=remote["name"], **report)
    return report


async def recall(remote: dict[str, Any], progress: Progress | None = None) -> dict[str, int]:
    """Bring every blob kept in *remote* back to the disk and delete it there."""
    session = grunt.get_session()
    rows = await grunt.db.get_all(
        "File",
        filters={"storage_remote": remote["name"]},
        fields=["content_hash", "file_size"],
        limit=None,
    )
    await session.commit()
    sizes = {r["content_hash"]: int(r["file_size"] or 0) for r in rows if r["content_hash"]}
    if not sizes:
        await _update_stats(remote)
        return {"files": 0, "bytes": 0}
    storage = _storage()
    total = sum(sizes.values())
    free = shutil.disk_usage(storage.root).free
    if total * 1.1 > free:
        raise RemoteError(
            _("Not enough free disk space: %(need)s MB needed, %(free)s MB free")
            % {"need": total // 2**20, "free": free // 2**20}
        )
    if progress is not None:
        progress.set(stage=_("Downloading %(n)s files") % {"n": len(sizes)}, total=total)
    staging = storage.root / "tmp" / f"recall-{uuid.uuid4().hex}"
    staging.mkdir(parents=True)
    keys = sorted(sizes)
    try:
        async with Rclone(remote) as rc:
            await rc.get_files(
                remote_dir(), [relative(k) for k in keys], staging, progress=progress
            )
            back: list[str] = []
            for key in keys:
                got = staging / relative(key)
                if not got.exists() or await asyncio.to_thread(_sha256, got) != key:
                    log.warning("cloud.recall_damaged", key=key, remote=remote["name"])
                    continue
                dest = storage.path(key)
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(got, dest)
                back.append(key)
            for chunk in _chunks(back):
                await grunt.db.bulk_update(
                    "File",
                    {"content_hash__in": chunk, "storage_remote": remote["name"]},
                    {"storage_remote": None},
                )
            await session.commit()
            await rc.delete_files([relative(k) for k in back], remote_dir())
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    await _update_stats(remote)
    if len(back) < len(keys):
        raise RemoteError(
            _("%(n)s files could not be returned (missing or damaged in the storage)")
            % {"n": len(keys) - len(back)}
        )
    report = {"files": len(back), "bytes": sum(sizes[k] for k in back)}
    log.info("cloud.recalled", remote=remote["name"], **report)
    return report


async def _update_stats(remote: dict[str, Any]) -> None:
    from grunt.monitoring.health import human_size

    [agg] = await grunt.db.aggregate(
        "File",
        filters={"storage_remote": remote["name"]},
        aggregations={"n": "count(name)", "size": "sum(file_size)"},
    )
    await grunt.db.set_value(
        "StorageRemote",
        remote["name"],
        {"offloaded_files": agg.get("n") or 0, "offloaded_size": human_size(agg.get("size") or 0)},
    )
    await grunt.get_session().commit()


# Garbage collection


async def needed_keys(remote_name: str) -> set[str]:
    """Blobs *remote_name* must keep: its live rows + unrestored trashed ones."""
    keys = set(
        await grunt.db.get_all(
            "File", filters={"storage_remote": remote_name}, pluck="content_hash", limit=None
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
        if isinstance(data, dict) and data.get("storage_remote") == remote_name:
            keys.add(data.get("content_hash"))
    keys.discard(None)
    return keys


async def collect_remote_garbage(grace_seconds: int) -> dict[str, int]:
    """Delete remote blobs nothing refers to; trim the local cache."""
    session = grunt.get_session()
    names = set(
        await grunt.db.get_all(
            "File", filters={"storage_remote__isnull": False}, pluck="storage_remote", limit=None
        )
    )
    current = await files_remote()
    if current:
        names.add(current["name"])
    remotes = []
    for name in sorted(names):
        try:
            remotes.append((await load_remote(name), await needed_keys(name)))
        except RemoteError:
            continue
    await session.commit()

    cutoff = datetime.now(UTC) - timedelta(seconds=grace_seconds)
    deleted = 0
    for remote, keep in remotes:
        if not remote.get("enabled"):
            continue
        try:
            async with Rclone(remote) as rc:
                stale = [
                    e["Path"]
                    for e in await rc.list(remote_dir(), recursive=True)
                    if Path(e["Path"]).name not in keep and _mtime(e) < cutoff
                ]
                await rc.delete_files(stale, remote_dir())
        except RemoteError as exc:
            await record_status(remote, exc)
            continue
        deleted += len(stale)
    limit = int((current or {}).get("cache_size_mb") or 0) * 2**20
    trimmed = await asyncio.to_thread(trim_cache, limit, time.time() - grace_seconds)
    return {"remote_deleted": deleted, "cache_trimmed": trimmed}


def _mtime(entry: dict[str, Any]) -> datetime:
    try:
        return datetime.fromisoformat(entry["ModTime"].replace("Z", "+00:00"))
    except KeyError, ValueError:
        return datetime.now(UTC)


def trim_cache(limit_bytes: int, older_than: float) -> int:
    """Drop the oldest-used cache copies until the cache fits *limit_bytes*.

    Copies used after *older_than* are kept regardless (just fetched for a
    reader). Returns how many were dropped.
    """
    root = cache_root()
    if not root.is_dir():
        return 0
    entries = []
    for path in root.glob("*/*/*"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        entries.append((stat.st_mtime, stat.st_size, path))
    total = sum(size for _m, size, _p in entries)
    removed = 0
    for mtime, size, path in sorted(entries):
        if total <= limit_bytes or mtime >= older_than:
            break
        path.unlink(missing_ok=True)
        total -= size
        removed += 1
    return removed


async def remote_listing(remote_name: str) -> set[str]:
    """Keys present in *remote_name* (for ``grunt files verify``)."""
    async with Rclone(await load_remote(remote_name)) as rc:
        return {Path(e["Path"]).name for e in await rc.list(remote_dir(), recursive=True)}
