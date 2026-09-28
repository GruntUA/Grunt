"""process_email_queue claims each row atomically so overlapping runs
(the on-commit kick racing the */5 cron) can't send a message twice."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from grunt.email.service import email_service


async def _queue_one(ctx) -> str:
    await ctx.new_doc("EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True})
    await ctx.db._session().commit()
    rid = await email_service.queue_email(
        session=ctx.db._session(),
        to="user@example.com",
        subject="Тема",
        body="Тіло",
    )
    await ctx.db._session().commit()
    return rid


@pytest.mark.asyncio
async def test_claim_is_exclusive(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        rid = await _queue_one(ctx)

        first = await ctx.db.bulk_update(
            "EmailQueue", {"name": rid, "status": "Pending"}, {"status": "Sending"}
        )
        second = await ctx.db.bulk_update(
            "EmailQueue", {"name": rid, "status": "Pending"}, {"status": "Sending"}
        )

    assert first == 1
    assert second == 0


@pytest.mark.asyncio
async def test_stale_sending_is_reopened_fresh_is_not(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        stale = await _queue_one(ctx)
        fresh = await _queue_one(ctx)

        # stale: claimed long ago
        await ctx.db.bulk_update(
            "EmailQueue",
            {"name": stale},
            {"status": "Sending", "modified_at": datetime.now(UTC) - timedelta(hours=1)},
        )
        # fresh: claimed just now
        await ctx.db.bulk_update(
            "EmailQueue",
            {"name": fresh},
            {"status": "Sending", "modified_at": datetime.now(UTC)},
        )

        reopened = await ctx.db.bulk_update(
            "EmailQueue",
            {
                "status": "Sending",
                "modified_at__lt": datetime.now(UTC) - timedelta(minutes=10),
            },
            {"status": "Pending"},
        )
        assert reopened == 1

        stale_status = await ctx.db.get_value("EmailQueue", stale, "status")
        fresh_status = await ctx.db.get_value("EmailQueue", fresh, "status")

    assert stale_status == "Pending"
    assert fresh_status == "Sending"


@pytest.mark.asyncio
async def test_process_email_queue_double_run_sends_once(ctx, monkeypatch):
    """Two overlapping process_email_queue runs → exactly one send_now."""
    from grunt.email import tasks as email_tasks
    from grunt.email.service import EmailService

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        rid = await _queue_one(ctx)

    sent: list = []

    async def _fake_send_now(account, message):
        # Yield so the two runs actually interleave around the claim.
        await asyncio.sleep(0)
        sent.append(message["name"])

    monkeypatch.setattr(EmailService, "send_now", staticmethod(_fake_send_now))

    import conftest as _cf

    monkeypatch.setattr(email_tasks.site_manager, "get_active_site", lambda: "test", raising=False)
    monkeypatch.setattr(
        email_tasks.site_manager,
        "get_session_maker",
        lambda _site: _cf.TestSessionLocal,
        raising=False,
    )
    monkeypatch.setattr(
        email_tasks.site_manager,
        "get_engine",
        lambda _site: _cf.test_engine,
        raising=False,
    )

    await asyncio.gather(
        email_tasks.process_email_queue(),
        email_tasks.process_email_queue(),
    )

    assert sent == [rid]

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        status = await ctx.db.get_value("EmailQueue", rid, "status")
    assert status == "Sent"
