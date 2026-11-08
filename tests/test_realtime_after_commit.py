"""Realtime messages and pushes announce a change - they go out after the commit."""

from typing import Any

import pytest
from sqlalchemy import select

from grunt.api.v1.ws import manager
from grunt.db.commit import drain
from grunt.metadata.compiler import OUTBOX_TABLE


@pytest.fixture
def sent(monkeypatch) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []

    async def send_to_user(user: str, payload: dict) -> None:
        out.append((user, payload["event"]))

    monkeypatch.setattr(manager, "send_to_user", send_to_user)
    return out


@pytest.mark.asyncio
async def test_publish_waits_for_the_commit(ctx, sent):
    session = ctx.db._session()
    await ctx.new_doc("ToDo", {"description": "x"})
    await ctx.publish(user="a@example.com", event="msgprint", message="saved")
    await drain()
    assert sent == []

    await session.commit()
    await drain()
    assert sent == [("a@example.com", "msgprint")]


@pytest.mark.asyncio
async def test_rolled_back_publish_is_never_sent(ctx, sent):
    session = ctx.db._session()
    await ctx.new_doc("ToDo", {"description": "x"})
    await ctx.publish(user="a@example.com", event="msgprint", message="saved")
    await session.rollback()
    await drain()
    assert sent == []


@pytest.mark.asyncio
async def test_publish_outside_a_transaction_goes_at_once(ctx, sent):
    await ctx.db._session().commit()
    await ctx.publish(user="a@example.com", event="msgprint", message="hi")
    await drain()
    assert sent == [("a@example.com", "msgprint")]


@pytest.mark.asyncio
async def test_notification_push_goes_through_the_outbox(ctx, sent):
    from grunt.notification.service import notification_service

    session = ctx.db._session()
    await notification_service.notify(
        session,
        user="Administrator",
        doctype="ToDo",
        doc_id="T-1",
        subject="Hello",
        message="World",
    )
    rows = [dict(r._mapping) for r in await session.execute(select(OUTBOX_TABLE))]
    assert [r["handler"] for r in rows] == ["grunt.webpush.service.deliver_push"]
    assert rows[0]["payload"]["subject"] == "Hello"
    await session.rollback()
    assert list(await session.execute(select(OUTBOX_TABLE))) == []
