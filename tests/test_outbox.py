"""The outbox: messages commit with the change, go out after it, failures retry.

Webhooks ride on it - a save no longer waits on the remote server.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from grunt import outbox
from grunt.db.commit import drain
from grunt.metadata.compiler import OUTBOX_TABLE
from grunt.testkit import sent_tasks

DELIVERED: list[dict[str, Any]] = []
FAIL_TIMES = {"n": 0}


async def record(payload: dict[str, Any]) -> None:
    DELIVERED.append(payload)


async def flaky(payload: dict[str, Any]) -> None:
    if FAIL_TIMES["n"] > 0:
        FAIL_TIMES["n"] -= 1
        raise RuntimeError("remote is down")
    DELIVERED.append(payload)


@pytest.fixture(autouse=True)
def _reset():
    DELIVERED.clear()
    FAIL_TIMES["n"] = 0
    yield
    DELIVERED.clear()


async def _rows(session) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in await session.execute(select(OUTBOX_TABLE))]


@pytest.mark.asyncio
async def test_message_commits_with_the_change(ctx):
    session = ctx.db._session()
    await outbox.put(record, {"n": 1})
    await session.rollback()
    assert await _rows(session) == []

    await outbox.put(record, {"n": 2})
    await session.commit()
    [row] = await _rows(session)
    assert row["handler"] == "tests.test_outbox.record"
    assert row["payload"] == {"n": 2}


@pytest.mark.asyncio
async def test_commit_kicks_one_delivery(ctx):
    session = ctx.db._session()
    before = len(sent_tasks)
    await outbox.put(record, {"n": 1})
    await outbox.put(record, {"n": 2})
    await drain()
    assert len(sent_tasks) == before  # nothing before the commit
    await session.commit()
    await drain()
    kicked = [m for m in sent_tasks[before:] if m.task_name.endswith("outbox:deliver")]
    assert len(kicked) == 1


@pytest.mark.asyncio
async def test_delivery_removes_the_message(ctx):
    session = ctx.db._session()
    await outbox.put(record, {"n": 1})
    await outbox.put(record, {"n": 2})
    await session.commit()

    assert await outbox.deliver_due(session) == 2
    assert DELIVERED == [{"n": 1}, {"n": 2}]
    assert await _rows(session) == []


@pytest.mark.asyncio
async def test_failure_is_retried_after_a_backoff(ctx):
    session = ctx.db._session()
    FAIL_TIMES["n"] = 1
    await outbox.put(flaky, {"n": 1})
    await session.commit()

    assert await outbox.deliver_due(session) == 0
    [row] = await _rows(session)
    assert row["attempts"] == 1
    assert row["last_error"] == "remote is down"
    assert row["claimed_until"] is None
    assert row["due_at"] > datetime.now(UTC)

    # not due yet - the next run leaves it
    assert await outbox.deliver_due(session) == 0
    assert DELIVERED == []

    await session.execute(update(OUTBOX_TABLE).values(due_at=datetime.now(UTC)))
    await session.commit()
    assert await outbox.deliver_due(session) == 1
    assert DELIVERED == [{"n": 1}]
    assert await _rows(session) == []


@pytest.mark.asyncio
async def test_given_up_after_max_attempts(ctx):
    session = ctx.db._session()
    FAIL_TIMES["n"] = 1000
    await outbox.put(flaky, {"n": 1})
    await session.commit()
    for _ in range(outbox.MAX_ATTEMPTS):
        await session.execute(update(OUTBOX_TABLE).values(due_at=datetime.now(UTC)))
        await session.commit()
        await outbox.deliver_due(session)
    assert await _rows(session) == []
    assert DELIVERED == []


@pytest.mark.asyncio
async def test_a_claimed_message_is_left_to_its_run(ctx):
    session = ctx.db._session()
    await outbox.put(record, {"n": 1})
    await session.commit()
    future = datetime.now(UTC) + timedelta(minutes=1)
    await session.execute(update(OUTBOX_TABLE).values(claimed_until=future))
    await session.commit()
    assert await outbox.deliver_due(session) == 0

    # a crashed run's claim runs out
    past = datetime.now(UTC) - timedelta(seconds=1)
    await session.execute(update(OUTBOX_TABLE).values(claimed_until=past))
    await session.commit()
    assert await outbox.deliver_due(session) == 1


def test_backoff_grows_and_is_capped():
    assert outbox.backoff(1) == timedelta(seconds=30)
    assert outbox.backoff(2) == timedelta(minutes=1)
    assert outbox.backoff(3) == timedelta(minutes=2)
    assert outbox.backoff(50) == timedelta(hours=6)


def test_handler_must_be_importable():
    async def local(payload):
        pass

    with pytest.raises(ValueError, match="module-level"):
        outbox._path(local)


# Webhooks


@pytest.fixture
async def webhook(ctx):
    await ctx.new_doc(
        "OutgoingWebhook",
        {
            "doctype_name": "ToDo",
            "event": "after_insert",
            "url": "https://hooks.example.com/todo",
            "is_enabled": True,
        },
    )
    await ctx.db._session().commit()


class _Response:
    def __init__(self, status: int) -> None:
        self.status_code = status
        self.text = "ok"


@pytest.fixture
def remote(monkeypatch):
    """A fake remote end: records the POSTs, answers with ``remote["status"]``."""
    import httpx2

    state: dict[str, Any] = {"status": 200, "posts": []}

    class _Client:
        def __init__(self, *a, **kw) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def post(self, url, content=None, headers=None):
            state["posts"].append((url, content))
            return _Response(state["status"])

    monkeypatch.setattr(httpx2, "AsyncClient", _Client)
    return state


async def _logs(ctx) -> list[dict[str, Any]]:
    return await ctx.db.get_all("WebhookLog", fields=["success", "status_code"], limit=None)


@pytest.mark.asyncio
async def test_save_does_not_wait_for_the_webhook(ctx, webhook, remote):
    session = ctx.db._session()
    await ctx.new_doc("ToDo", {"description": "ping"})
    assert remote["posts"] == []  # nothing sent inside the transaction
    await session.commit()

    [row] = await _rows(session)
    assert row["handler"] == "grunt.webhook.service.deliver_webhook"

    assert await outbox.deliver_due(session) == 1
    [(url, body)] = remote["posts"]
    assert url == "https://hooks.example.com/todo"
    assert '"after_insert"' in body
    assert await _logs(ctx) == [{"success": True, "status_code": 200}]


@pytest.mark.asyncio
async def test_failed_webhook_is_retried_and_every_attempt_logged(ctx, webhook, remote):
    session = ctx.db._session()
    remote["status"] = 503
    await ctx.new_doc("ToDo", {"description": "ping"})
    await session.commit()

    assert await outbox.deliver_due(session) == 0
    [row] = await _rows(session)
    assert row["attempts"] == 1

    remote["status"] = 200
    await session.execute(update(OUTBOX_TABLE).values(due_at=datetime.now(UTC)))
    await session.commit()
    assert await outbox.deliver_due(session) == 1
    logs = await _logs(ctx)
    assert sorted(log["status_code"] for log in logs) == [200, 503]


@pytest.mark.asyncio
async def test_disabled_webhook_is_skipped(ctx, webhook, remote):
    session = ctx.db._session()
    await ctx.new_doc("ToDo", {"description": "ping"})
    await session.commit()
    name = await ctx.db.get_value("OutgoingWebhook", {"doctype_name": "ToDo"}, "name")
    await ctx.db.set_value("OutgoingWebhook", name, "is_enabled", False)
    await session.commit()

    assert await outbox.deliver_due(session) == 1  # handled - nothing to send
    assert remote["posts"] == []
    assert await _rows(session) == []
