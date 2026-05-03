"""Storage backends — local filesystem and S3-compatible object storage.

Config (via config.py / .env):
  STORAGE_BACKEND=local          (default)
  STORAGE_BACKEND=s3
  S3_BUCKET=my-bucket
  S3_REGION=eu-central-1
  S3_ENDPOINT_URL=               (optional, for MinIO / Cloudflare R2)
  AWS_ACCESS_KEY_ID=
  AWS_SECRET_ACCESS_KEY=

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

import structlog

logger = structlog.get_logger()

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
        logger.debug("storage.local.saved", path=rel_path)
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


class S3StorageBackend(StorageBackend):
    """Stores files in an S3-compatible bucket via aioboto3."""

    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url or None
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key

    def _session(self):
        try:
            import aioboto3  # noqa: PLC0415
        except ImportError as e:
            raise ImportError("pip install aioboto3 to use S3 storage backend") from e
        kwargs = {}
        if self._access_key_id:
            kwargs["aws_access_key_id"] = self._access_key_id
        if self._secret_access_key:
            kwargs["aws_secret_access_key"] = self._secret_access_key
        return aioboto3.Session(**kwargs)

    async def save(self, content: bytes, filename: str, content_type: str) -> str:
        validate_mime_type(content_type)
        ext = Path(filename).suffix.lower()
        today = date.today()
        key = f"{today.year}/{today.month:02d}/{uuid.uuid4().hex}{ext}"
        kw = dict(endpoint_url=self._endpoint_url) if self._endpoint_url else {}
        async with self._session().client("s3", region_name=self._region, **kw) as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
        logger.debug("storage.s3.saved", key=key, bucket=self._bucket)
        return key

    async def get(self, path: str) -> bytes:
        kw = dict(endpoint_url=self._endpoint_url) if self._endpoint_url else {}
        async with self._session().client("s3", region_name=self._region, **kw) as s3:
            resp = await s3.get_object(Bucket=self._bucket, Key=path)
            return await resp["Body"].read()

    async def delete(self, path: str) -> None:
        kw = dict(endpoint_url=self._endpoint_url) if self._endpoint_url else {}
        async with self._session().client("s3", region_name=self._region, **kw) as s3:
            await s3.delete_object(Bucket=self._bucket, Key=path)

    def public_url(self, path: str) -> str:
        if self._endpoint_url:
            return f"{self._endpoint_url}/{self._bucket}/{path}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{path}"


_backends: dict[str, StorageBackend] = {}
_s3_backend: StorageBackend | None = None


def _resolve_local_upload_dir(site: str) -> str:
    """Return the uploads directory for the given site."""
    from grunt.site.manager import site_manager  # noqa: PLC0415

    return str(site_manager.sites_dir / site / "uploads")


def get_storage_backend() -> StorageBackend:
    """Return the storage backend for the current site."""
    global _s3_backend

    from grunt.config import settings  # noqa: PLC0415

    if settings.storage_backend == "s3":
        if _s3_backend is None:
            _s3_backend = S3StorageBackend(
                bucket=settings.s3_bucket or "grunt-uploads",
                region=settings.s3_region or "us-east-1",
                endpoint_url=settings.s3_endpoint_url or None,
                access_key_id=settings.aws_access_key_id or None,
                secret_access_key=settings.aws_secret_access_key or None,
            )
            logger.info("storage.backend", type="s3", bucket=settings.s3_bucket)
        return _s3_backend

    from grunt.site.manager import current_site  # noqa: PLC0415

    site = current_site.get("")
    if not site:
        # fallback outside of a site context (e.g. tests)
        upload_dir = settings.upload_dir
    else:
        upload_dir = _resolve_local_upload_dir(site)

    if upload_dir not in _backends:
        _backends[upload_dir] = LocalStorageBackend(upload_dir)
        logger.info("storage.backend", type="local", site=site, dir=upload_dir)

    return _backends[upload_dir]
