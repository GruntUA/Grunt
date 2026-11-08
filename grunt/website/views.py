"""Page views of public documents - any DocType with a ``view_count`` field.

A page sends a beacon to :func:`record_view` after it loads
(``navigator.sendBeacon("/api/v1/method/grunt.website.views.record_view?doctype=…&name=…")``),
so bots without JS don't count and the HTML stays the same for every reader
(it can be cached). Known bots by User-Agent and a repeat view of the same page
from the same address within :data:`REPEAT_SECONDS` don't count either;
``SystemSettings.count_page_views`` turns counting off.

With Redis, views pile up in a hash per site and :func:`flush` (scheduler,
every minute) moves them to the DB with one ``UPDATE ... + n`` per page.
Without Redis each view is written right away.
"""

import re
from typing import Any

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy import func

import grunt
from grunt import log
from grunt.api.context import whitelist
lazy from grunt.auth.doctypes.UserSession.user_session import client_ip
lazy from grunt.config import settings
lazy from grunt.site.manager import current_site, site_manager
lazy from grunt.site.settings import get_setting
lazy from grunt.utils.redis import connect

FIELD = "view_count"
REPEAT_SECONDS = 30 * 60
_PREFIX = "grunt:views"
_NAME_RE = re.compile(r"^[\w-]{1,140}$")
_BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|headless|curl|wget|python|httpx", re.I
)

_client: Redis | None = None


def _redis() -> Redis | None:
    global _client

    if not settings.redis_url:
        return None
    if _client is None:
        _client = connect(socket_connect_timeout=1)
    return _client


def _pending_key(site: str) -> str:
    return f"{_PREFIX}:{site}"


async def _counted_meta(doctype: str) -> Any:
    """The DocType's meta when its documents count views (have ``view_count``)."""

    dt = await grunt.get_meta(doctype) if _NAME_RE.match(doctype or "") else None
    return dt if dt is not None and any(f.fieldname == FIELD for f in dt.fields) else None


async def counted(doctype: str) -> bool:
    """Whether *doctype*'s documents count views."""
    return await _counted_meta(doctype) is not None


async def record(doctype: str, name: str, ip: str, user_agent: str) -> bool:
    """Count a view of *name*; ``False`` - not counted (a bot, a repeat, junk,
    or a DocType without ``view_count``). The caller holds a grunt context."""

    if not _NAME_RE.match(name or "") or not await counted(doctype):
        return False
    if not user_agent or _BOT_RE.search(user_agent):
        return False
    key = f"{doctype}:{name}"
    redis = _redis()
    if redis is not None:
        pending = _pending_key(current_site.get())
        try:
            if not await redis.set(f"{pending}:seen:{key}:{ip}", 1, nx=True, ex=REPEAT_SECONDS):
                return False
            await redis.hincrby(pending, key, 1)
            return True
        except Exception as e:  # noqa: BLE001 - no Redis: write to the DB directly
            log.warning("website.views.redis_failed", error=str(e))
    await _apply({key: 1})
    return True


@whitelist(allow_guest=True)
async def record_view(doctype: str, name: str, request: Request | None = None) -> None:
    """A page view - the beacon a public page sends after it loads."""

    if request is None or not await get_setting("count_page_views", True):
        return
    user_agent = request.headers.get("user-agent") or ""
    await record(doctype, name, client_ip(request) or "unknown", user_agent)


async def _apply(counts: dict[str, int]) -> None:
    """``view_count += n`` per ``"<doctype>:<name>"`` key (the caller holds a context)."""

    for key, n in counts.items():
        doctype, _sep, name = key.partition(":")
        dt = await _counted_meta(doctype)
        if dt is None:
            continue
        column = dt.table.c[FIELD]
        await grunt.db.set_value(doctype, name, {FIELD: func.coalesce(column, 0) + n})


async def _flush_site(redis: Redis, site: str) -> int:
    pending = _pending_key(site)
    flushing = f"{pending}:flushing"
    # RENAME is atomic: views during the move go to a fresh hash. A hash left
    # over from a failed run is moved first (RENAME would overwrite it).
    if not await redis.exists(flushing):
        if not await redis.exists(pending):
            return 0
        await redis.rename(pending, flushing)
    raw: dict[Any, Any] = await redis.hgetall(flushing)
    counts = {
        (k.decode() if isinstance(k, bytes) else str(k)): int(v)
        for k, v in raw.items()
        if int(v) > 0
    }
    if counts:
        maker = site_manager.get_session_maker(site)
        async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
            await _apply(counts)
            await session.commit()
    await redis.delete(flushing)
    total = sum(counts.values())
    log.info("website.views.flushed", site=site, pages=len(counts), views=total)
    return total


async def flush() -> int:
    """Move the views gathered in Redis to each site's DB; the number of views moved."""

    redis = _redis()
    if redis is None:
        return 0
    total = 0
    for site in site_manager.get_sites():
        try:
            total += await _flush_site(redis, site)
        except Exception as e:  # noqa: BLE001 - one site must not hold up the others
            log.warning("website.views.flush_failed", site=site, error=str(e))
    return total
