"""Cache invalidation across processes.

Every web worker and every task worker keeps its own in-memory caches (DocType
definitions, compiled Tables, workflows, settings, the memory layer of
``QueryCache``/``DocumentCache``...). A write handled by one process drops
them there only; the others would serve the old value until a TTL or a restart.

With Redis the dropping is broadcast: a function decorated with :func:`fanout`
runs here as usual and is then re-run, with the same arguments and under the
same site, in every other process subscribed to ``grunt:invalidate``. Without
Redis there is nothing to tell - a bench without Redis runs one web process.

Inside a transaction a message waits for its commit (and is dropped on a
rollback): told any earlier, another process would re-read the old row before
the commit and cache it again. Delivery is best-effort and asynchronous (a
pub/sub message, well under a millisecond on a local Redis); the TTLs stay as
the backstop for a lost one.
"""

import asyncio
import functools
import inspect
import json
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from uuid import uuid4

from grunt.db.commit import drain as drain_commits
from grunt.db.commit import on_commit
from grunt.local import _engine_ctx, _session_ctx
from grunt.log import log
lazy from grunt.config import settings
lazy from grunt.site.manager import current_site, site_manager
lazy from grunt.utils.redis import connect, shared

CHANNEL = "grunt:invalidate"

# Tells this process's own messages apart from the others'.
SENDER = uuid4().hex

_PLAIN = (str, int, float, bool, type(None))
_handlers: dict[str, Callable[..., Any]] = {}
_listener: asyncio.Task[None] | None = None


def subscribe(topic: str, handler: Callable[..., Any]) -> None:
    """Run *handler* (sync or async) when another process publishes *topic*."""
    _handlers[topic] = handler


def publish(topic: str, **kwargs: Any) -> None:
    """Tell the other processes about *topic* - after the ambient transaction
    commits, or right away outside one (fire-and-forget).

    Callable from sync code. Without Redis, or outside an event loop, the
    message is dropped.
    """
    if not settings.redis_url:
        return
    message = json.dumps(
        {"sender": SENDER, "topic": topic, "site": current_site.get(), "kwargs": kwargs}
    )
    on_commit(lambda: _send(message))


async def _send(message: str) -> None:
    client = shared.get()
    if client is None:
        return
    try:
        await client.publish(CHANNEL, message)
    except Exception as exc:  # noqa: BLE001 - the TTL still bounds the staleness
        shared.failed("cache_bus.publish_failed", exc)


async def drain() -> None:
    """Wait for the messages still being sent (shutdown, tests)."""
    await drain_commits()


def fanout[F: Callable[..., Any]](fn: F) -> F:
    """Make an invalidation function run in every process, not just this one.

    Only plain keyword-or-positional values (str, int, float, bool, None) are
    forwarded; anything else - the ``doc`` a doc-event hook passes - is dropped,
    so a decorated function must not depend on it.
    """
    topic = f"{fn.__module__}.{fn.__qualname__}"
    subscribe(topic, fn)
    names = list(inspect.signature(fn).parameters)

    def _plain_kwargs(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
        merged = dict(zip(names, args, strict=False)) | kwargs
        return {k: v for k, v in merged.items() if isinstance(v, _PLAIN)}

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await fn(*args, **kwargs)
            publish(topic, **_plain_kwargs(args, kwargs))
            return result

        return async_wrapper  # pyright: ignore[reportReturnType]

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = fn(*args, **kwargs)
        publish(topic, **_plain_kwargs(args, kwargs))
        return result

    return wrapper  # pyright: ignore[reportReturnType]


def local[F: Callable[..., Any]](fn: F) -> F:
    """The undecorated function of a :func:`fanout` one - for work every process
    does on its own anyway (startup loads), which must not be broadcast."""
    return getattr(fn, "__wrapped__", fn)


async def handle(raw: str | bytes) -> None:
    """Run the handler of one received message (skipping our own)."""
    try:
        message = json.loads(raw)
    except ValueError:
        return
    if message.get("sender") == SENDER:
        return
    handler = _handlers.get(message.get("topic", ""))
    if handler is None:
        return
    site = message.get("site") or ""
    token = current_site.set(site)
    try:
        result = handler(**message.get("kwargs") or {})
        if inspect.isawaitable(result):
            await _await_in_site(site, result)
    except Exception as exc:  # noqa: BLE001 - one bad handler must not stop the listener
        log.warning("cache_bus.handler_failed", topic=message.get("topic"), error=str(exc))
    finally:
        current_site.reset(token)


async def _await_in_site(site: str, awaitable: Any) -> None:
    """Async handlers may read the DB (``grunt.db``): give them a session of *site*.

    No user is bound - an invalidation acts on no one's behalf.
    """
    if site not in site_manager.get_sites():
        await awaitable
        return
    async with site_manager.get_session_maker(site)() as session:
        tokens = (_session_ctx.set(session), _engine_ctx.set(site_manager.get_engine(site)))
        try:
            await awaitable
        finally:
            _session_ctx.reset(tokens[0])
            _engine_ctx.reset(tokens[1])


async def _listen() -> None:
    while True:
        client = connect()
        try:
            pubsub = client.pubsub()
            await pubsub.subscribe(CHANNEL)
            log.debug("cache_bus.listening", sender=SENDER)
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    await handle(msg["data"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reconnect after a Redis restart
            log.warning("cache_bus.listener_error", error=str(exc))
            await asyncio.sleep(2)
        finally:
            with suppress(Exception):
                await client.aclose()


def start() -> None:
    """Subscribe this process (web server and task worker startup)."""
    global _listener
    if not settings.redis_url or (_listener is not None and not _listener.done()):
        return
    _listener = asyncio.get_running_loop().create_task(_listen())


async def stop() -> None:
    global _listener
    await drain()
    if _listener is not None:
        _listener.cancel()
        with suppress(asyncio.CancelledError):
            await _listener
        _listener = None
