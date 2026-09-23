"""Per-document cache for hot get-by-id lookups.

``QueryCache`` caches *lists*, keyed by a whole query signature. This caches a
single document's data, keyed by ``(doctype, name)`` — the shape needed by a
hot "load this one document on every request" path. The first consumer is
``grunt.auth.doctypes.User.user.get_auth_context_user`` (the profile+roles
lookup ``current_user``/``optional_user`` run on nearly every request), but
nothing here is auth-specific: any doctype with a similar hot get-by-id path
can use it the same way.

Same in-memory-always / Redis-when-configured layering as ``QueryCache``, and
invalidated through the same choke point (``DocumentAPI._invalidate_list_cache``,
which already runs on every write to keep ``QueryCache`` fresh). The TTL is a
backstop for a write path that bypasses that hook (or a Redis outage), not the
primary freshness mechanism — invalidation is.
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from grunt.log import log

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from redis.asyncio import Redis

from grunt.config import settings


class DocumentCache:
    """Cache one document's data per ``(doctype, name)``."""

    def __init__(self, *, ttl_seconds: int | None = None) -> None:
        self._ttl_seconds = int(ttl_seconds or settings.doc_cache_ttl_seconds)
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._redis_failed = False

    def _key(self, doctype: str, name: str) -> str:
        return f"doccache:{doctype}:{name}"

    def _key_prefix(self, doctype: str) -> str:
        return f"doccache:{doctype}:"

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

    @asynccontextmanager
    async def _redis(self) -> AsyncGenerator[Redis | None]:
        if self._redis_failed or not settings.redis_url:
            yield None
            return
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
        try:
            yield r
        finally:
            await r.aclose()

    async def get(self, doctype: str, name: str) -> dict[str, Any] | None:
        key = self._key(doctype, name)
        payload = self._get_memory(key)
        if payload is not None:
            return payload

        try:
            async with self._redis() as r:
                if r is None:
                    return None
                raw = await r.get(key)
        except Exception as exc:
            self._redis_failed = True
            log.warning("doc_cache.redis_get_failed", error=str(exc))
            return None
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        payload = json.loads(raw)
        self._set_memory(key, payload)
        return payload

    async def set(self, doctype: str, name: str, payload: dict[str, Any]) -> None:
        # Normalize once (some columns, e.g. created_at/modified_at, are
        # datetimes) so a memory hit and a Redis hit return an identically
        # shaped payload — callers that don't read those fields back as
        # datetimes (the auth path doesn't) are unaffected either way.
        raw = json.dumps(payload, separators=(",", ":"), default=str)
        key = self._key(doctype, name)
        self._set_memory(key, json.loads(raw))
        try:
            async with self._redis() as r:
                if r is None:
                    return
                await r.setex(key, self._ttl_seconds, raw)
        except Exception as exc:
            self._redis_failed = True
            log.warning("doc_cache.redis_set_failed", error=str(exc))

    async def invalidate(self, doctype: str, name: str) -> None:
        key = self._key(doctype, name)
        self._memory.pop(key, None)
        try:
            async with self._redis() as r:
                if r is None:
                    return
                await r.delete(key)
        except Exception as exc:
            self._redis_failed = True
            log.warning("doc_cache.redis_invalidate_failed", error=str(exc))

    async def invalidate_doctype(self, doctype: str) -> None:
        """Drop every cached document of this doctype — used when a write
        touches an unknown set of names (e.g. a filtered bulk update)."""
        prefix = self._key_prefix(doctype)
        stale = [k for k in self._memory if k.startswith(prefix)]
        for k in stale:
            self._memory.pop(k, None)

        try:
            async with self._redis() as r:
                if r is None:
                    return
                keys = await r.keys(f"{prefix}*")
                if keys:
                    await r.delete(*keys)
        except Exception as exc:
            self._redis_failed = True
            log.warning(
                "doc_cache.redis_invalidate_doctype_failed", error=str(exc), doctype=doctype
            )

    async def invalidate_all(self) -> None:
        """Drop every cached document of every doctype (test/dev reset)."""
        self._memory.clear()
        try:
            async with self._redis() as r:
                if r is None:
                    return
                keys = await r.keys("doccache:*")
                if keys:
                    await r.delete(*keys)
        except Exception as exc:
            self._redis_failed = True
            log.warning("doc_cache.redis_invalidate_all_failed", error=str(exc))

    def clear(self) -> None:
        self._memory.clear()
