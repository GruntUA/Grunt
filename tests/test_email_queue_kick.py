"""queue_email nudges process_email_queue on commit, not on rollback."""

from __future__ import annotations

import asyncio

import pytest

from grunt.email import tasks as email_tasks
from grunt.email.service import email_service


async def _settle() -> None:
    """Let the after-commit hook's fire-and-forget task run."""
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_commit_kicks_the_queue(ctx, monkeypatch):
    calls: list[tuple] = []

    async def _fake_kiq(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(email_tasks.process_email_queue, "kiq", _fake_kiq)

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        await email_service.queue_email(
            session=ctx.db._session(),
            to="user@example.com",
            subject="Тема",
            body="Тіло",
        )
        # Nothing fired yet — the row is still uncommitted.
        await _settle()
        assert calls == []

        await ctx.db._session().commit()
        await _settle()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_rollback_does_not_kick_the_queue(ctx, monkeypatch):
    calls: list[tuple] = []

    async def _fake_kiq(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(email_tasks.process_email_queue, "kiq", _fake_kiq)

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        await email_service.queue_email(
            session=ctx.db._session(),
            to="user@example.com",
            subject="Тема",
            body="Тіло",
        )
        await ctx.db._session().rollback()
        await _settle()

    assert calls == []


@pytest.mark.asyncio
async def test_many_queue_calls_share_one_kick(ctx, monkeypatch):
    calls: list[tuple] = []

    async def _fake_kiq(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(email_tasks.process_email_queue, "kiq", _fake_kiq)

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        for i in range(3):
            await email_service.queue_email(
                session=ctx.db._session(),
                to=f"user{i}@example.com",
                subject="Тема",
                body="Тіло",
            )
        await ctx.db._session().commit()
        await _settle()

    assert len(calls) == 1
