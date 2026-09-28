from __future__ import annotations

import pytest

import grunt.progress as progress_mod
from grunt.progress import track_progress


@pytest.fixture
def sent(monkeypatch):
    events: list[tuple[str, str, dict]] = []

    async def fake_send(user, event, data):
        events.append((user, event, data))

    async def no_redis():
        return None

    monkeypatch.setattr(progress_mod, "_send", fake_send)
    monkeypatch.setattr(progress_mod, "_redis", no_redis)
    return events


@pytest.mark.asyncio
async def test_progress_is_published_and_finished(sent):
    async with track_progress("Backup", user="a@x", total=200, doctype="Backup") as p:
        p.set(stage="Copying")
        p.advance(50)
        await progress_mod.asyncio.sleep(0)  # let the flusher run once

    progress = [d for _u, e, d in sent if e == "task_progress"]
    assert progress[-1]["percent"] == 25
    assert progress[-1]["description"] == "Copying"
    user, event, done = sent[-1]
    assert (user, event) == ("a@x", "task_done")
    assert done["status"] == "done" and done["doctype"] == "Backup"


@pytest.mark.asyncio
async def test_failure_is_reported_and_raised(sent):
    with pytest.raises(RuntimeError):
        async with track_progress("Backup", user="a@x"):
            raise RuntimeError("disk full")
    assert sent[-1][1] == "task_done"
    assert sent[-1][2]["status"] == "error"
    assert sent[-1][2]["message"] == "disk full"


@pytest.mark.asyncio
async def test_without_a_user_nothing_is_sent(sent):
    async with track_progress("Backup", user=None, total=10) as p:
        p.advance(10)
    assert sent == []


def test_percent_never_reaches_100_before_done():
    p = progress_mod.Progress("x", user=None, total=10)
    p.advance(10)
    assert p.payload()["percent"] == 99


class FakeRedis:
    def __init__(self, store):
        self.store = store

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def exists(self, key):
        return int(key in self.store)

    async def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)

    async def aclose(self):
        pass


@pytest.fixture
def redis_store(monkeypatch, sent):
    store: dict = {}

    async def fake_redis():
        return FakeRedis(store)

    monkeypatch.setattr(progress_mod, "_redis", fake_redis)
    return store


def _as_user(monkeypatch, email):
    import grunt
    from tests.support import make_user

    monkeypatch.setattr(grunt, "get_user", lambda: make_user(email))


@pytest.mark.asyncio
async def test_cancel_stops_the_task_and_reports_cancelled(sent, redis_store, monkeypatch):
    _as_user(monkeypatch, "a@x")
    async with track_progress("Backup", user="a@x", total=100, cancellable=True) as p:
        await progress_mod.asyncio.sleep(0)  # flusher stores the task
        assert p.payload()["cancellable"] is True
        assert await progress_mod.cancel_task(p.task_id) is True
        await progress_mod.asyncio.sleep(progress_mod.FLUSH_SECONDS + 0.05)
        p.advance(1)  # raises TaskCancelledError; track_progress swallows it
        raise AssertionError("not reached")  # pragma: no cover
    assert sent[-1][1] == "task_done" and sent[-1][2]["status"] == "cancelled"
    assert redis_store == {}  # state and cancel flag are cleaned up


@pytest.mark.asyncio
async def test_someone_elses_task_cannot_be_cancelled(sent, redis_store, monkeypatch):
    async with track_progress("Backup", user="a@x", cancellable=True) as p:
        await progress_mod.asyncio.sleep(0)
        _as_user(monkeypatch, "b@x")
        assert await progress_mod.cancel_task(p.task_id) is False


@pytest.mark.asyncio
async def test_without_redis_a_task_is_not_cancellable(sent):
    async with track_progress("Backup", user="a@x", cancellable=True) as p:
        assert p.payload()["cancellable"] is False
