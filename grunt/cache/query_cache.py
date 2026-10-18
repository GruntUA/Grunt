"""Query-level cache for read-heavy list endpoints.

Uses in-memory storage always and Redis (optional) when configured. Keys carry
the site; an invalidation also drops the memory layer of every other process
(:mod:`grunt.cache.bus`).
"""

import hashlib
import json
import time
from typing import Any

from grunt.cache import bus
from grunt.config import settings
from grunt.document.base import DocumentList
from grunt.site.manager import current_site
lazy from grunt.utils.redis import shared

_DROP = "query_cache.drop"


class QueryCache:
    """Cache Document list responses by query signature."""

    def __init__(self, *, ttl_seconds: int | None = None) -> None:
        self._ttl_seconds = int(ttl_seconds or settings.query_cache_ttl_seconds)
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._hits = 0
        self._misses = 0

    def _key_prefix(self, doctype: str) -> str:
        return f"qcache:{current_site.get()}:list:{doctype}:"

    def _count_key_prefix(self, doctype: str) -> str:
        return f"qcache:{current_site.get()}:count:{doctype}:"

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
        include_total: bool = True,
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
            "include_total": include_total,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self._key_prefix(doctype)}{digest}"

    def build_count_key(
        self,
        *,
        doctype: str,
        user_email: str,
        filters: dict[str, Any] | None,
    ) -> str:
        payload = {"doctype": doctype, "user": user_email, "filters": filters or {}}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self._count_key_prefix(doctype)}{digest}"

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
        r = shared.get()
        if r is None:
            return None
        try:
            raw = await r.get(key)
        except Exception as exc:
            shared.failed("query_cache.redis_get_failed", exc)
            return None
        return json.loads(raw) if raw else None

    async def _set_redis(self, key: str, payload: dict[str, Any]) -> None:
        r = shared.get()
        if r is None:
            return
        try:
            await r.set(key, json.dumps(payload, separators=(",", ":")), ex=self._ttl_seconds)
        except Exception as exc:
            shared.failed("query_cache.redis_set_failed", exc)

    async def get_list(self, key: str) -> DocumentList | None:
        payload = self._get_memory(key)
        if payload is not None:
            self._hits += 1
            return DocumentList(
                data=list(payload.get("data", [])), meta=dict(payload.get("meta", {}))
            )

        payload = await self._get_redis(key)
        if payload is not None:
            self._hits += 1
            self._set_memory(key, payload)
            return DocumentList(
                data=list(payload.get("data", [])), meta=dict(payload.get("meta", {}))
            )

        self._misses += 1
        return None

    async def set_list(self, key: str, result: DocumentList) -> None:
        payload = {"data": list(result), "meta": dict(result.meta)}
        self._set_memory(key, payload)
        await self._set_redis(key, payload)

    async def get_count(self, key: str) -> int | None:
        payload = self._get_memory(key)
        if payload is not None:
            self._hits += 1
            return int(payload["n"])

        payload = await self._get_redis(key)
        if payload is not None:
            self._hits += 1
            self._set_memory(key, payload)
            return int(payload["n"])

        self._misses += 1
        return None

    async def set_count(self, key: str, value: int) -> None:
        payload = {"n": value}
        self._set_memory(key, payload)
        await self._set_redis(key, payload)

    def drop_memory(self, doctype: str) -> None:
        """Forget this process's cached pages and counts of ``doctype``."""
        prefixes = (self._key_prefix(doctype), self._count_key_prefix(doctype))
        for k in [k for k in self._memory if k.startswith(prefixes)]:
            self._memory.pop(k, None)

    async def invalidate_doctype(self, doctype: str) -> None:
        """Drop every cached list page and count for ``doctype``.

        Both namespaces share one invalidation call because they're driven by
        the same event (a doc of this type was created/updated/deleted) - a
        caller never needs to invalidate one without the other.
        """
        self.drop_memory(doctype)
        bus.publish(_DROP, doctype=doctype)
        prefixes = (self._key_prefix(doctype), self._count_key_prefix(doctype))

        # Now and once more after the commit - see DocumentCache._drop.
        async def purge() -> None:
            r = shared.get()
            if r is None:
                return
            try:
                keys = []
                for prefix in prefixes:
                    keys.extend([k async for k in r.scan_iter(match=f"{prefix}*")])
                if keys:
                    await r.delete(*keys)
            except Exception as exc:
                shared.failed("query_cache.redis_invalidate_failed", exc)

        await purge()
        bus.after_commit(purge)

    def subscribe(self) -> None:
        """Let the other processes' invalidations reach this cache's memory."""
        bus.subscribe(_DROP, self.drop_memory)

    def clear(self) -> None:
        self._memory.clear()

    def stats(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "keys": len(self._memory),
        }
