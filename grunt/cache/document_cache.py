"""Per-document cache for hot get-by-id lookups.

``QueryCache`` caches *lists*, keyed by a whole query signature. This caches a
single document's data, keyed by ``(doctype, name)`` - the shape needed by a
hot "load this one document on every request" path. The first consumer is
``grunt.auth.doctypes.User.user.get_auth_context_user`` (the profile+roles
lookup ``current_user``/``optional_user`` run on nearly every request), but
nothing here is auth-specific: any doctype with a similar hot get-by-id path
can use it the same way.

Same in-memory-always / Redis-when-configured layering as ``QueryCache``, and
invalidated through the same choke point (``DocumentAPI._invalidate_list_cache``,
which already runs on every write to keep ``QueryCache`` fresh). The other
processes drop their memory copy via :mod:`grunt.cache.bus`. The TTL is a
backstop for a write path that bypasses that hook (or a Redis outage), not the
primary freshness mechanism - invalidation is.

Keys carry the site: one bench serves several sites from one Redis, and
``User`` names (emails) repeat across them.
"""

import json
import time
from typing import Any

from grunt.cache import bus
from grunt.config import settings
from grunt.site.manager import current_site
from grunt.utils.redis import shared

_DROP = "doc_cache.drop"


class DocumentCache:
    """Cache one document's data per ``(doctype, name)``."""

    def __init__(self, *, ttl_seconds: int | None = None) -> None:
        self._ttl_seconds = int(ttl_seconds or settings.doc_cache_ttl_seconds)
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}

    def _key_prefix(self, doctype: str | None = None) -> str:
        site_prefix = f"doccache:{current_site.get()}:"
        return f"{site_prefix}{doctype}:" if doctype else site_prefix

    def _key(self, doctype: str, name: str) -> str:
        return f"{self._key_prefix(doctype)}{name}"

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

    def drop_memory(self, doctype: str | None = None, name: str | None = None) -> None:
        """Forget this process's copies: one document, a doctype, or the site's all."""
        if doctype and name:
            self._memory.pop(self._key(doctype, name), None)
            return
        prefix = self._key_prefix(doctype)
        for k in [k for k in self._memory if k.startswith(prefix)]:
            self._memory.pop(k, None)

    async def _drop(self, doctype: str | None = None, name: str | None = None) -> None:
        """Drop here, in Redis and (via the bus) in every other process.

        Redis is purged now and once more after the commit: in between another
        process may have cached the not-yet-committed old row again.
        """
        self.drop_memory(doctype, name)
        bus.publish(_DROP, doctype=doctype, name=name)
        pattern = None if doctype and name else f"{self._key_prefix(doctype)}*"
        key = self._key(doctype, name) if doctype and name else None

        async def purge() -> None:
            r = shared.get()
            if r is None:
                return
            try:
                if key is not None:
                    await r.delete(key)
                else:
                    keys = [k async for k in r.scan_iter(match=pattern)]
                    if keys:
                        await r.delete(*keys)
            except Exception as exc:
                shared.failed("doc_cache.redis_invalidate_failed", exc)

        await purge()
        bus.after_commit(purge)

    async def get(self, doctype: str, name: str) -> dict[str, Any] | None:
        key = self._key(doctype, name)
        payload = self._get_memory(key)
        if payload is not None:
            return payload

        r = shared.get()
        if r is None:
            return None
        try:
            raw = await r.get(key)
        except Exception as exc:
            shared.failed("doc_cache.redis_get_failed", exc)
            return None
        if not raw:
            return None
        payload = json.loads(raw)
        self._set_memory(key, payload)
        return payload

    async def set(self, doctype: str, name: str, payload: dict[str, Any]) -> None:
        # Normalize once (some columns, e.g. created_at/modified_at, are
        # datetimes) so a memory hit and a Redis hit return an identically
        # shaped payload - callers that don't read those fields back as
        # datetimes (the auth path doesn't) are unaffected either way.
        raw = json.dumps(payload, separators=(",", ":"), default=str)
        key = self._key(doctype, name)
        self._set_memory(key, json.loads(raw))
        r = shared.get()
        if r is None:
            return
        try:
            await r.set(key, raw, ex=self._ttl_seconds)
        except Exception as exc:
            shared.failed("doc_cache.redis_set_failed", exc)

    async def invalidate(self, doctype: str, name: str) -> None:
        await self._drop(doctype, name)

    async def invalidate_doctype(self, doctype: str) -> None:
        """Drop every cached document of this doctype - used when a write
        touches an unknown set of names (e.g. a filtered bulk update)."""
        await self._drop(doctype)

    async def invalidate_all(self) -> None:
        """Drop every cached document of the current site (test/dev reset)."""
        await self._drop()

    def clear(self) -> None:
        self._memory.clear()

    def subscribe(self) -> None:
        """Let the other processes' invalidations reach this cache's memory."""
        bus.subscribe(_DROP, self.drop_memory)
