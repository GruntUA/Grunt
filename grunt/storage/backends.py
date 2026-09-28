"""Storage backends — content-addressed blobs, per site.

A blob's key is the SHA-256 of its bytes, so identical content is stored once
no matter how many ``File`` rows point at it, and a stored blob never changes.
On the local filesystem (``sites/<site>/uploads/``)::

    blobs/ab/cd/abcd…  — the file itself (no extension: ``File`` has the type)
    thumbs/ab/cd/abcd….webp — its preview (grunt.storage.thumbnails)
    tmp/               — uploads in flight, moved into ``blobs/`` when complete

Usage::

    from grunt.storage import get_storage_backend
    storage = get_storage_backend()
    key, size = await storage.put(stream_or_bytes, max_bytes=...)
    content = await storage.get(key)

Blobs are never deleted when a ``File`` row goes — several rows may share
one — but by :func:`grunt.storage.gc.collect_garbage`, which drops those no
row (nor a trashed row) refers to any more.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from grunt import log

if TYPE_CHECKING:
    from collections.abc import Iterator

CHUNK_SIZE = 1024 * 1024
_KEY_RE = re.compile(r"^[0-9a-f]{64}$")


class FileTooLargeError(ValueError):
    """The content is over the size limit passed to ``put``."""


class StorageBackend(ABC):
    @abstractmethod
    async def put(
        self, source: bytes | BinaryIO, *, max_bytes: int | None = None
    ) -> tuple[str, int]:
        """Store *source*; return ``(key, size)``. Storing known content is a no-op."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Return the blob's bytes; FileNotFoundError when there is none."""

    @abstractmethod
    def path(self, key: str) -> Path:
        """Local path of the blob (for streaming responses)."""

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Drop the blob and its preview."""

    @abstractmethod
    async def put_thumbnail(self, key: str, content: bytes) -> None: ...

    @abstractmethod
    def thumbnail_path(self, key: str) -> Path: ...

    @abstractmethod
    def iter_keys(self) -> Iterator[tuple[str, float]]:
        """Every stored blob as ``(key, mtime)``."""

    @abstractmethod
    def sweep_tmp(self, older_than: float) -> int:
        """Remove in-flight uploads abandoned before *older_than* (epoch seconds)."""


def _check_key(key: str) -> str:
    # Keys come from the DB, but they become paths — never let one escape the root.
    if not _KEY_RE.match(key or ""):
        raise FileNotFoundError(f"Invalid storage key: {key!r}")
    return key


class LocalStorageBackend(StorageBackend):
    """Stores blobs on the local filesystem under the site's ``uploads/``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _shard(self, folder: str, key: str, suffix: str = "") -> Path:
        key = _check_key(key)
        return self.root / folder / key[:2] / key[2:4] / f"{key}{suffix}"

    def path(self, key: str) -> Path:
        return self._shard("blobs", key)

    def thumbnail_path(self, key: str) -> Path:
        return self._shard("thumbs", key, ".webp")

    def _put_sync(self, source: BinaryIO, max_bytes: int | None) -> tuple[str, int]:
        tmp_dir = self.root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tmp_dir / uuid.uuid4().hex
        digest = hashlib.sha256()
        size = 0
        try:
            with tmp.open("wb") as out:
                while chunk := source.read(CHUNK_SIZE):
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise FileTooLargeError(size)
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            key = digest.hexdigest()
            dest = self.path(key)
            if dest.exists():
                # Known content: keep the stored copy, but freshen its mtime so
                # the garbage collector's grace period covers the File row
                # that is about to point at it.
                os.utime(dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp, dest)  # atomic: a blob is complete or absent
            return key, size
        finally:
            tmp.unlink(missing_ok=True)

    async def put(
        self, source: bytes | BinaryIO, *, max_bytes: int | None = None
    ) -> tuple[str, int]:
        stream = io.BytesIO(source) if isinstance(source, bytes | bytearray) else source
        key, size = await asyncio.to_thread(self._put_sync, stream, max_bytes)
        log.debug("storage.local.put", key=key, size=size)
        return key, size

    async def get(self, key: str) -> bytes:
        full = self.path(key)
        if not full.exists():
            raise FileNotFoundError(f"File not found: {key}")
        return await asyncio.to_thread(full.read_bytes)

    async def exists(self, key: str) -> bool:
        return self.path(key).exists()

    async def delete(self, key: str) -> None:
        for full in (self.path(key), self.thumbnail_path(key)):
            await asyncio.to_thread(full.unlink, True)

    def _write_sync(self, dest: Path, content: bytes) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f".{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(content)
        os.replace(tmp, dest)

    async def put_thumbnail(self, key: str, content: bytes) -> None:
        await asyncio.to_thread(self._write_sync, self.thumbnail_path(key), content)

    def iter_keys(self) -> Iterator[tuple[str, float]]:
        blobs = self.root / "blobs"
        if not blobs.is_dir():
            return
        for path in blobs.glob("*/*/*"):
            if _KEY_RE.match(path.name):
                yield path.name, path.stat().st_mtime

    def sweep_tmp(self, older_than: float) -> int:
        removed = 0
        for folder in (self.root / "tmp", self.root / "thumbs"):
            if not folder.is_dir():
                continue
            pattern = "*" if folder.name == "tmp" else "*/*/.*.tmp"
            for path in folder.glob(pattern):
                if path.is_file() and path.stat().st_mtime < older_than:
                    path.unlink(missing_ok=True)
                    removed += 1
        return removed


_backends: dict[str, StorageBackend] = {}


def _resolve_local_upload_dir(site: str) -> str:
    """Return the uploads directory for the given site."""
    from grunt.site.manager import site_manager

    return str(site_manager.sites_dir / site / "uploads")


def get_storage_backend() -> StorageBackend:
    """Return the storage backend for the current site."""
    from grunt.config import settings
    from grunt.site.manager import site_manager

    try:
        # Not just current_site: task workers and the CLI bind none, and used
        # to write into ./uploads of whatever directory they ran in.
        site = site_manager.get_active_site()
    except ValueError:
        site = ""
    upload_dir = settings.upload_dir if not site else _resolve_local_upload_dir(site)

    if upload_dir not in _backends:
        _backends[upload_dir] = LocalStorageBackend(upload_dir)
        log.info("storage.backend", type="local", site=site, dir=upload_dir)

    return _backends[upload_dir]
