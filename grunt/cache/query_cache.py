"""Query-level cache for read-heavy list endpoints.

Uses in-memory storage always and Redis (optional) when configured.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import structlog

from grunt.config import settings
from grunt.document.base import DocumentList

logger = structlog.get_logger()


class QueryCache:
    """Cache Document list responses by query signature."""

    def __init__(self, *, ttl_seconds: int | None = None) -> None:
        self._ttl_seconds = int(ttl_seconds or settings.query_cache_ttl_seconds)
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._hits = 0
        self._misses = 0
        self._redis_failed = False

    def _key_prefix(self, doctype: str) -> str:
        return f"qcache:list:{doctype}:"

    def build_key(
        self,
        *,
        doctype: str,
        user_email: str,
        filters: dict[str, Any] | None,
        fields: list[str] | None,
        limit: int,
        page: int,
        order_by: str,
        order: str,
        search: str | None,
    ) -> str:
        payload = {
            "doctype": doctype,
            "user": user_email,
            "filters": filters or {},
            "fields": fields or [],
            "limit": int(limit),
            "page": int(page),
            "order_by": order_by,
            "order": order,
            "search": search or "",
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self._key_prefix(doctype)}{digest}"

    def _get_memory(self, key: str) -> dict[str, Any] | None:
        item = self._memory.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if expires_at <= time.time():
            self._memory.pop(key, None)
            return None
        return payload

    def _set_memory(self, key: str, payload: dict[str, Any]) -> None:
        self._memory[key] = (time.time() + self._ttl_seconds, payload)

    async def _get_redis(self, key: str) -> dict[str, Any] | None:
        if self._redis_failed or not settings.redis_url:
            return None
        try:
            import redis.asyncio as aioredis  # noqa: PLC0415

            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
            raw = await r.get(key)
            await r.aclose()
            if not raw:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode()
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            self._redis_failed = True
            logger.warning("query_cache.redis_get_failed", error=str(exc))
            return None

    async def _set_redis(self, key: str, payload: dict[str, Any]) -> None:
        if self._redis_failed or not settings.redis_url:
            return
        try:
            import redis.asyncio as aioredis  # noqa: PLC0415

            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
            await r.setex(key, self._ttl_seconds, json.dumps(payload, separators=(",", ":")))
            await r.aclose()
        except Exception as exc:  # noqa: BLE001
            self._redis_failed = True
            logger.warning("query_cache.redis_set_failed", error=str(exc))

    async def get_list(self, key: str) -> DocumentList | None:
        payload = self._get_memory(key)
        if payload is not None:
            self._hits += 1
            return DocumentList(data=list(payload.get("data", [])), meta=dict(payload.get("meta", {})))

        payload = await self._get_redis(key)
        if payload is not None:
            self._hits += 1
            self._set_memory(key, payload)
            return DocumentList(data=list(payload.get("data", [])), meta=dict(payload.get("meta", {})))

        self._misses += 1
        return None

    async def set_list(self, key: str, result: DocumentList) -> None:
        payload = {"data": list(result), "meta": dict(result.meta)}
        self._set_memory(key, payload)
        await self._set_redis(key, payload)

    async def invalidate_doctype(self, doctype: str) -> None:
        prefix = self._key_prefix(doctype)
        stale = [k for k in self._memory if k.startswith(prefix)]
        for k in stale:
            self._memory.pop(k, None)

        if self._redis_failed or not settings.redis_url:
            return
        try:
            import redis.asyncio as aioredis  # noqa: PLC0415

            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
            keys = await r.keys(f"{prefix}*")
            if keys:
                await r.delete(*keys)
            await r.aclose()
        except Exception as exc:  # noqa: BLE001
            self._redis_failed = True
            logger.warning("query_cache.redis_invalidate_failed", error=str(exc), doctype=doctype)

    def clear(self) -> None:
        self._memory.clear()

    def stats(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "keys": len(self._memory),
        }
