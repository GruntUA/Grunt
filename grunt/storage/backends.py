"""Storage backends — files live on the local filesystem, per site.

Usage::

    from grunt.storage import get_storage_backend
    storage = get_storage_backend()
    url = await storage.save(content=b"...", filename="file.pdf", content_type="application/pdf")
    content = await storage.get(path)
    await storage.delete(path)
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from grunt import log

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


def validate_mime_type(content_type: str) -> None:
    """Raise ValueError if the MIME type is not in the allowlist."""
    base_type = content_type.split(";")[0].strip().lower()
    if base_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"File type '{base_type}' is not allowed")


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, content: bytes, filename: str, content_type: str) -> str:
        """Save content and return a path/key for later retrieval."""

    @abstractmethod
    async def get(self, path: str) -> bytes:
        """Return file contents by path/key."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a file by path/key."""

    @abstractmethod
    def public_url(self, path: str) -> str:
        """Return a URL to access the file (may be an API proxy URL)."""


class LocalStorageBackend(StorageBackend):
    """Stores files on the local filesystem under UPLOAD_DIR."""

    def __init__(self, upload_dir: str) -> None:
        self._root = Path(upload_dir)

    async def save(self, content: bytes, filename: str, content_type: str) -> str:
        validate_mime_type(content_type)
        ext = Path(filename).suffix.lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        today = date.today()
        rel_dir = Path(str(today.year)) / f"{today.month:02d}"
        abs_dir = self._root / rel_dir
        abs_dir.mkdir(parents=True, exist_ok=True)
        path = abs_dir / unique_name
        await asyncio.to_thread(path.write_bytes, content)
        rel_path = str(rel_dir / unique_name)
        log.debug("storage.local.saved", path=rel_path)
        return rel_path

    async def get(self, path: str) -> bytes:
        full = self._root / path
        if not full.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return await asyncio.to_thread(full.read_bytes)

    async def delete(self, path: str) -> None:
        full = self._root / path
        if full.exists():
            await asyncio.to_thread(full.unlink)

    def public_url(self, path: str) -> str:
        # Served via the /api/v1/files/{id} endpoint (path is opaque to callers)
        return f"/api/v1/files/{path}"


_backends: dict[str, StorageBackend] = {}


def _resolve_local_upload_dir(site: str) -> str:
    """Return the uploads directory for the given site."""
    from grunt.site.manager import site_manager

    return str(site_manager.sites_dir / site / "uploads")


def get_storage_backend() -> StorageBackend:
    """Return the storage backend for the current site."""
    from grunt.config import settings
    from grunt.site.manager import current_site

    site = current_site.get("")
    upload_dir = settings.upload_dir if not site else _resolve_local_upload_dir(site)

    if upload_dir not in _backends:
        _backends[upload_dir] = LocalStorageBackend(upload_dir)
        log.info("storage.backend", type="local", site=site, dir=upload_dir)

    return _backends[upload_dir]
