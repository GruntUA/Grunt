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
