"""Several web workers share one Redis: cache invalidations reach the other
processes (after the commit), one process leads the scheduler, and the rate
limit, idempotency store and WebSocket presence span all of them.

Runs against a real local Redis (database 15); skipped without one.
"""

import asyncio
import json

import pytest
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from grunt.api.v1 import ws
from grunt.cache import bus
from grunt.cache.document_cache import DocumentCache
from grunt.config import settings
from grunt.local import _session_ctx
from grunt.middleware.idempotency import IdempotencyMiddleware
from grunt.middleware.rate_limit import RateLimitMiddleware
from grunt.site.manager import current_site
from grunt.tasks import scheduler
from grunt.utils.redis import shared

REDIS_URL = "redis://localhost:6379/15"


async def _redis_up() -> bool:
    client = aioredis.from_url(REDIS_URL, socket_connect_timeout=0.5)
    try:
        return bool(await client.ping())
    except Exception:  # noqa: BLE001
        return False
    finally:
        await client.aclose()


@pytest.fixture
async def redis(monkeypatch):
    if not await _redis_up():
        pytest.skip("no local Redis")
    monkeypatch.setattr(settings, "redis_url", REDIS_URL)
    monkeypatch.setattr(shared, "_client", None)
    monkeypatch.setattr(shared, "_retry_at", 0.0)
    client = aioredis.from_url(REDIS_URL)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
    await shared.aclose()


async def _own_message(pubsub, timeout: float):
    """The next message this process published, or None.

    Pub/sub ignores the database number, so under xdist the channel also carries
    other workers' messages - skip those.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while (left := deadline - loop.time()) > 0:
        msg = await pubsub.get_message(timeout=left)
        if msg and msg["type"] == "message" and json.loads(msg["data"])["sender"] == bus.SENDER:
            return msg
    return None


async def test_message_from_another_process_runs_the_handler(monkeypatch):
    calls = []
    monkeypatch.setitem(bus._handlers, "t.probe", lambda **kw: calls.append(kw))

    await bus.handle(json.dumps({"sender": "other", "topic": "t.probe", "kwargs": {"x": 1}}))
    await bus.handle(json.dumps({"sender": bus.SENDER, "topic": "t.probe", "kwargs": {"x": 2}}))

    assert calls == [{"x": 1}]


async def test_handler_runs_under_the_senders_site(monkeypatch):
    seen = []
    monkeypatch.setitem(bus._handlers, "t.site", lambda: seen.append(current_site.get()))
    await bus.handle(json.dumps({"sender": "other", "topic": "t.site", "site": "b.example"}))
    assert seen == ["b.example"]


async def test_fanout_forwards_plain_arguments_only(redis, monkeypatch):
    sent = []
    monkeypatch.setattr(bus, "publish", lambda topic, **kw: sent.append((topic, kw)))

    @bus.fanout
    def drop(name: str, **_kwargs: object) -> None:
        pass

    drop("Task", doc=object(), flag=True)
    [(topic, kwargs)] = sent
    assert topic.endswith(".drop")
    assert kwargs == {"name": "Task", "flag": True}


async def test_message_waits_for_the_commit_and_dies_with_a_rollback(redis):
    pubsub = redis.pubsub()
    await pubsub.subscribe(bus.CHANNEL)
    await pubsub.get_message(timeout=1)  # subscribe confirmation

    engine = create_async_engine("sqlite+aiosqlite://")
    async with AsyncSession(engine) as session:
        token = _session_ctx.set(session)
        try:
            await session.begin()
            bus.publish("t.rolled_back")
            await session.rollback()

            await session.begin()
            bus.publish("t.committed")
            await bus.drain()
            assert await _own_message(pubsub, 0.2) is None  # not before the commit
            await session.commit()
            await bus.drain()
        finally:
            _session_ctx.reset(token)
    await engine.dispose()

    msg = await _own_message(pubsub, 1)
    assert msg is not None and json.loads(msg["data"])["topic"] == "t.committed"
    assert await _own_message(pubsub, 0.2) is None
    await pubsub.aclose()


async def test_doc_cache_keys_are_per_site(redis):
    cache = DocumentCache(ttl_seconds=60)
    token = current_site.set("a.example")
    await cache.set("User", "x@example.com", {"site": "a"})
    current_site.reset(token)

    token = current_site.set("b.example")
    try:
        cache.clear()
        assert await cache.get("User", "x@example.com") is None
    finally:
        current_site.reset(token)


async def test_doc_cache_invalidation_drops_other_processes_memory(redis, monkeypatch):
    here, there = DocumentCache(ttl_seconds=60), DocumentCache(ttl_seconds=60)
    monkeypatch.setitem(bus._handlers, "doc_cache.drop", there.drop_memory)
    pubsub = redis.pubsub()
    await pubsub.subscribe(bus.CHANNEL)
    await pubsub.get_message(timeout=1)

    await there.set("User", "x@example.com", {"v": 1})
    await here.invalidate("User", "x@example.com")
    await bus.drain()
    msg = await _own_message(pubsub, 1)
    await pubsub.aclose()
    assert msg is not None

    # "there" receives what "here" sent.
    monkeypatch.setattr(bus, "SENDER", "another-process")
    await bus.handle(msg["data"])
    assert there._get_memory(there._key("User", "x@example.com")) is None
    assert await there.get("User", "x@example.com") is None


async def test_one_process_leads_the_scheduler(redis, monkeypatch):
    monkeypatch.setattr(scheduler, "_RENEW_EVERY", 0.05)
    monkeypatch.setattr(scheduler, "is_leader", False)
    started = []

    async def lead():
        scheduler.is_leader = True
        started.append(True)

    monkeypatch.setattr(scheduler, "_lead", lead)
    await redis.set(scheduler.LEADER_KEY, "other-host:1:abc", ex=30)

    election = asyncio.create_task(scheduler._elect())
    await asyncio.sleep(0.2)
    assert not started  # someone else holds the key
    assert await scheduler.current_leader() == "other-host:1:abc"

    await redis.delete(scheduler.LEADER_KEY)  # the leader went away
    await asyncio.sleep(0.2)
    assert started == [True]
    assert await scheduler.current_leader() == scheduler.IDENTITY

    election.cancel()
    with pytest.raises(asyncio.CancelledError):
        await election
    assert await redis.get(scheduler.LEADER_KEY) is None  # released on stop


async def test_leader_steps_down_when_the_key_is_taken(redis, monkeypatch):
    monkeypatch.setattr(scheduler, "_RENEW_EVERY", 0.05)
    monkeypatch.setattr(scheduler, "is_leader", True)
    stepped = []
    monkeypatch.setattr(scheduler, "_step_down", lambda: stepped.append(True))
    await redis.set(scheduler.LEADER_KEY, "other-host:1:abc", ex=30)

    election = asyncio.create_task(scheduler._elect())
    await asyncio.sleep(0.2)
    election.cancel()
    with pytest.raises(asyncio.CancelledError):
        await election
    assert stepped
    assert await redis.get(scheduler.LEADER_KEY) == b"other-host:1:abc"


async def test_rate_limit_is_shared_by_workers(redis):
    first, second = RateLimitMiddleware(None), RateLimitMiddleware(None)
    assert (await first._check("ip:1.2.3.4", 2))[0]
    assert (await second._check("ip:1.2.3.4", 2))[0]
    allowed, remaining, reset_in = await first._check("ip:1.2.3.4", 2)
    assert not allowed and remaining == 0 and 0 <= reset_in <= 60


async def test_idempotent_replay_from_another_worker(redis):
    first, second = IdempotencyMiddleware(None), IdempotencyMiddleware(None)
    await first._put("idem:h|u|k", (201, b'{"name": "T-1"}', "application/json"))
    assert await second._get("idem:h|u|k") == (201, b'{"name": "T-1"}', "application/json")


class _Socket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


async def test_presence_lists_viewers_of_every_worker(redis, monkeypatch):
    channel = "doc:Task:T-1"
    here, there = ws.ConnectionManager(), ws.ConnectionManager()
    a, b = _Socket(), _Socket()

    monkeypatch.setattr(ws, "SENDER", "proc-there")
    await there.presence_join(channel, b, {"email": "b@example.com"})  # pyright: ignore[reportArgumentType]
    monkeypatch.setattr(ws, "SENDER", "proc-here")
    await here.presence_join(channel, a, {"email": "a@example.com"})  # pyright: ignore[reportArgumentType]
    for manager in (here, there):
        if manager._heartbeat_task is not None:
            manager._heartbeat_task.cancel()

    emails = sorted(u["email"] for u in await here._presence_all(channel))
    assert emails == ["a@example.com", "b@example.com"]

    # "there" crashed: its heartbeat expires, its viewers drop out of the list.
    await redis.delete(ws._ALIVE_KEY + "proc-there")
    assert [u["email"] for u in await here._presence_all(channel)] == ["a@example.com"]
