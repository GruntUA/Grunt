"""SQLite: a transaction that reads first and writes later fails *at once* with
"database is locked" when another connection committed in between (WAL can't
upgrade a stale snapshot; busy_timeout is not consulted). Work that intends to
write starts with BEGIN IMMEDIATE instead and simply waits for the lock."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from grunt.db import write_intent


def test_begin_statement_follows_intent(monkeypatch):
    monkeypatch.setattr(write_intent, "_process_default", False)
    assert write_intent.begin_statement() == "BEGIN"
    write_intent.set_write_intent(True)
    assert write_intent.begin_statement() == "BEGIN IMMEDIATE"
    write_intent.set_write_intent(False)
    monkeypatch.setattr(write_intent, "_process_default", True)
    assert write_intent.begin_statement() == "BEGIN"  # explicit intent wins


def test_process_default_applies_without_explicit_intent(monkeypatch):
    import contextvars

    monkeypatch.setattr(write_intent, "_process_default", True)
    fresh = contextvars.Context()
    assert fresh.run(write_intent.begin_statement) == "BEGIN IMMEDIATE"


def _engine(path):
    eng = create_async_engine(f"sqlite+aiosqlite:///{path}", connect_args={"timeout": 5})

    @event.listens_for(eng.sync_engine, "connect")
    def _connect(dbapi_conn, _):
        dbapi_conn.isolation_level = None
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    @event.listens_for(eng.sync_engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql(write_intent.begin_statement())

    return eng


async def _read_then_write(eng, other, intent: bool):
    write_intent.set_write_intent(intent)
    async with eng.connect() as a:
        await a.execute(text("select n from t"))  # starts the transaction
        if not intent:
            # Another process commits while we hold a (deferred) read snapshot.
            async with other.connect() as b:
                await b.execute(text("update t set n = n + 1"))
                await b.commit()
        await a.execute(text("update t set n = n + 10"))
        await a.commit()


@pytest.mark.asyncio
async def test_deferred_read_then_write_fails_immediately(tmp_path):
    eng = _engine(tmp_path / "db.sqlite")
    other = _engine(tmp_path / "db.sqlite")
    async with eng.begin() as c:
        await c.execute(text("create table t (n int)"))
        await c.execute(text("insert into t values (0)"))
    with pytest.raises(OperationalError, match="locked"):
        await _read_then_write(eng, other, intent=False)
    await eng.dispose()
    await other.dispose()


@pytest.mark.asyncio
async def test_immediate_writer_makes_the_other_wait(tmp_path):
    eng = _engine(tmp_path / "db.sqlite")
    other = _engine(tmp_path / "db.sqlite")
    async with eng.begin() as c:
        await c.execute(text("create table t (n int)"))
        await c.execute(text("insert into t values (0)"))

    async def competing_writer():
        write_intent.set_write_intent(True)
        await asyncio.sleep(0.05)  # starts while the first one holds the lock
        async with other.connect() as b:
            await b.execute(text("update t set n = n + 1"))
            await b.commit()

    async def first():
        write_intent.set_write_intent(True)
        async with eng.connect() as a:
            await a.execute(text("select n from t"))
            await asyncio.sleep(0.2)
            await a.execute(text("update t set n = n + 10"))
            await a.commit()

    await asyncio.gather(first(), competing_writer())
    async with eng.connect() as c:
        assert (await c.execute(text("select n from t"))).scalar() == 11
    await eng.dispose()
    await other.dispose()
