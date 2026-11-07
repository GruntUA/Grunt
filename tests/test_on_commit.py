"""``grunt.db.commit.on_commit`` - side effects wait for the commit, a rollback drops them."""

import pytest

from grunt.db.commit import drain, on_commit


def _recorder(calls: list[str], label: str):
    async def fn() -> None:
        calls.append(label)

    return fn


async def _write(ctx) -> None:
    """Open the transaction with a write, as a save does."""
    await ctx.new_doc("ToDo", {"description": "on_commit"})


@pytest.mark.asyncio
async def test_runs_after_commit(ctx):
    calls: list[str] = []
    await _write(ctx)
    on_commit(_recorder(calls, "a"))
    await drain()
    assert calls == []  # still uncommitted

    await ctx.db._session().commit()
    await drain()
    assert calls == ["a"]


@pytest.mark.asyncio
async def test_rollback_drops_it(ctx):
    calls: list[str] = []
    await _write(ctx)
    on_commit(_recorder(calls, "a"))
    await ctx.db._session().rollback()
    await drain()
    assert calls == []

    # the next transaction starts clean
    await _write(ctx)
    await ctx.db._session().commit()
    await drain()
    assert calls == []


@pytest.mark.asyncio
async def test_savepoint_rollback_keeps_the_outer_work(ctx):
    calls: list[str] = []
    session = ctx.db._session()
    await _write(ctx)
    on_commit(_recorder(calls, "outer"))
    savepoint = await session.begin_nested()
    await savepoint.rollback()
    await session.commit()
    await drain()
    assert calls == ["outer"]


@pytest.mark.asyncio
async def test_key_runs_once_per_transaction(ctx):
    calls: list[str] = []
    await _write(ctx)
    for _ in range(3):
        on_commit(_recorder(calls, "kick"), key="kick")
    await ctx.db._session().commit()
    await drain()
    assert calls == ["kick"]

    await _write(ctx)
    on_commit(_recorder(calls, "kick"), key="kick")
    await ctx.db._session().commit()
    await drain()
    assert calls == ["kick", "kick"]


@pytest.mark.asyncio
async def test_without_a_transaction_runs_now(ctx):
    calls: list[str] = []
    await ctx.db._session().commit()  # nothing open
    on_commit(_recorder(calls, "now"))
    await drain()
    assert calls == ["now"]


@pytest.mark.asyncio
async def test_an_error_is_logged_not_raised(ctx):
    async def boom() -> None:
        raise RuntimeError("remote is down")

    calls: list[str] = []
    await _write(ctx)
    on_commit(boom)
    on_commit(_recorder(calls, "after"))
    await ctx.db._session().commit()
    await drain()
    assert calls == ["after"]
