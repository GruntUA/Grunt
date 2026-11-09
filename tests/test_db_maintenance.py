"""SQLite connection tuning and the nightly maintenance task."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from grunt.db.dialects import dialect_for
from grunt.tasks import db_maintenance


@pytest.fixture
async def sqlite_engine(tmp_path):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'm.db'}")
    dialect = dialect_for(eng)
    dialect.setup_engine(eng)
    yield eng
    await eng.dispose()


async def test_connection_pragmas(sqlite_engine):
    async with sqlite_engine.connect() as conn:
        auto_vacuum = (await conn.execute(text("PRAGMA auto_vacuum"))).scalar()
        cache = (await conn.execute(text("PRAGMA cache_size"))).scalar()
        temp = (await conn.execute(text("PRAGMA temp_store"))).scalar()
        mmap = (await conn.execute(text("PRAGMA mmap_size"))).scalar()
    assert auto_vacuum == 2  # INCREMENTAL - set before WAL, or it never applies
    assert cache == -32768
    assert temp == 2  # MEMORY
    assert mmap == 268435456


async def test_maintenance_collects_stats_and_frees_pages(sqlite_engine, monkeypatch):
    async with sqlite_engine.begin() as conn:
        await conn.execute(text("CREATE TABLE t (k TEXT, v TEXT)"))
        await conn.execute(text("CREATE INDEX ix_t_k ON t (k)"))
        for i in range(2000):
            await conn.execute(
                text("INSERT INTO t VALUES (:k, :v)"), {"k": str(i % 50), "v": "x" * 200}
            )
        await conn.execute(text("DELETE FROM t WHERE rowid > 100"))

    async with sqlite_engine.connect() as conn:
        assert (await conn.execute(text("PRAGMA freelist_count"))).scalar() > 10

    monkeypatch.setattr(db_maintenance.site_manager, "get_active_site", lambda: "s")
    monkeypatch.setattr(db_maintenance.site_manager, "get_engine", lambda _site: sqlite_engine)
    await db_maintenance.run_maintenance()

    async with sqlite_engine.connect() as conn:
        free = (await conn.execute(text("PRAGMA freelist_count"))).scalar()
        stats = (
            await conn.execute(
                text("SELECT count(*) FROM sqlite_master WHERE name = 'sqlite_stat1'")
            )
        ).scalar()
    assert free == 0
    assert stats == 1
