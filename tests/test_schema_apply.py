"""``grunt.db.schema`` against a real database - the plan applied by the dialect.

Runs on the test backend (SQLite, or PostgreSQL with ``TEST_DATABASE_URL``).
"""

import pytest
import sqlalchemy as sa

from grunt.db.dialects import dialect_for
from grunt.db.schema import AlterType, diff, read_actual
from grunt.db.schema.apply import DuplicateDataError, apply, check

NAME = "grunt_test_schema_item"


def _table(*, qty_type=sa.Integer, unique=True, index=True, extra=()) -> sa.Table:
    meta = sa.MetaData()
    status = sa.Column("status", sa.String(140))
    status.info["backfill_default"] = "Open"
    items = [
        sa.Column("name", sa.String(255), primary_key=True),
        sa.Column("qty", qty_type()),
        sa.Column("code", sa.String(140)),
        status,
        *extra,
    ]
    if unique:
        items.append(sa.UniqueConstraint("code", name=f"uq_{NAME}_code"))
    if index:
        items.append(sa.Index(f"ix_{NAME}_status", "status"))
    return sa.Table(NAME, meta, *items)


async def _sync(engine, table, **kw) -> list:
    """Plan *table* against the database, check and apply it; returns the plan."""
    rebuild = kw.pop("rebuild", False)

    def run(conn):
        dialect = dialect_for(conn)
        changes = diff(
            table,
            read_actual(conn, NAME),
            sa_dialect=conn.dialect,
            can_alter_type=dialect.can_alter_column_type,
            **kw,
        )
        apply(conn, dialect, check(conn, dialect, changes), rebuild=rebuild)
        return changes

    async with engine.begin() as conn:
        return await conn.run_sync(run)


async def _actual(engine):
    async with engine.connect() as conn:
        return await conn.run_sync(read_actual, NAME)


async def _rows(engine, sql: str) -> list:
    async with engine.connect() as conn:
        return list((await conn.execute(sa.text(sql))).all())


@pytest.fixture
async def engine(engine):
    yield engine
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"DROP TABLE IF EXISTS {NAME}"))


@pytest.mark.asyncio
async def test_create_then_nothing_to_do(engine):
    await _sync(engine, _table())
    assert await _sync(engine, _table()) == []


@pytest.mark.asyncio
async def test_added_column_is_backfilled(engine):
    meta = sa.MetaData()
    sa.Table(NAME, meta, sa.Column("name", sa.String(255), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(meta.create_all)
        await conn.execute(sa.text(f"INSERT INTO {NAME} (name) VALUES ('a')"))

    await _sync(engine, _table(unique=False, index=False))
    assert await _rows(engine, f"SELECT status FROM {NAME}") == [("Open",)]


@pytest.mark.asyncio
async def test_unique_over_duplicates_is_refused_and_nothing_changes(engine):
    await _sync(engine, _table(unique=False))
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(f"INSERT INTO {NAME} (name, code) VALUES ('a', 'X'), ('b', 'X')")
        )
        await conn.execute(sa.text(f"INSERT INTO {NAME} (name, code) VALUES ('c', ''), ('d', '')"))

    with pytest.raises(DuplicateDataError) as exc:
        await _sync(engine, _table())
    assert exc.value.duplicates[0]["value"] == "X"
    assert f"uq_{NAME}_code" not in (await _actual(engine)).unique_indexes


@pytest.mark.asyncio
async def test_unique_leaves_empty_values_out(engine):
    await _sync(engine, _table(unique=False))
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"INSERT INTO {NAME} (name, code) VALUES ('c', ''), ('d', '')"))
    await _sync(engine, _table())
    assert f"uq_{NAME}_code" in (await _actual(engine)).unique_indexes


@pytest.mark.asyncio
async def test_stale_index_is_dropped_only_when_asked(engine):
    old = sa.Column("old", sa.Integer)
    await _sync(engine, _table(extra=[old, sa.Index(f"ix_{NAME}_old", "old")]))
    current = _table(extra=[sa.Column("old", sa.Integer)])

    await _sync(engine, current)
    assert f"ix_{NAME}_old" in (await _actual(engine)).indexes

    await _sync(engine, current, drop_indexes=True)
    assert f"ix_{NAME}_old" not in (await _actual(engine)).indexes


@pytest.mark.asyncio
async def test_dropped_column_takes_its_index_first(engine):
    legacy = sa.Column("legacy", sa.Integer)
    await _sync(engine, _table(extra=[legacy, sa.Index(f"ix_{NAME}_legacy", "legacy")]))
    await _sync(engine, _table(), drop_columns=True)
    actual = await _actual(engine)
    assert "legacy" not in actual.columns
    assert f"ix_{NAME}_legacy" not in actual.indexes


@pytest.mark.asyncio
async def test_type_change_keeps_the_rows(engine):
    await _sync(engine, _table(qty_type=sa.Integer))
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"INSERT INTO {NAME} (name, qty, code) VALUES ('a', 7, 'X')"))

    plan = await _sync(engine, _table(qty_type=lambda: sa.String(140)), rebuild=True)
    assert [type(c) for c in plan] == [AlterType]
    actual = await _actual(engine)
    assert isinstance(actual.columns["qty"], sa.String)
    assert await _rows(engine, f"SELECT qty, code FROM {NAME}") == [("7", "X")]
    # indexes and the unique survive a rebuild
    assert f"ix_{NAME}_status" in actual.indexes
    assert f"uq_{NAME}_code" in actual.uniques | actual.unique_indexes


@pytest.mark.asyncio
async def test_a_rebuild_waits_for_migrate(engine):
    await _sync(engine, _table(qty_type=sa.Integer))
    async with engine.connect() as conn:
        can_alter = dialect_for(conn).can_alter_column_type
    await _sync(engine, _table(qty_type=lambda: sa.String(140)))  # not allowed to rebuild
    changed = isinstance((await _actual(engine)).columns["qty"], sa.String)
    assert changed is can_alter  # PostgreSQL alters in place; SQLite waits


@pytest.mark.asyncio
async def test_migrate_dry_run_prints_the_plan(ctx, engine):
    from grunt.api.v1.meta import save_doctype
    from grunt.metadata.compiler import invalidate_table_cache, preview_sync
    from grunt.metadata.field import DocField

    await save_doctype(
        doctype_data={
            "name": "SchemaPlanItem",
            "label": "Schema Plan Item",
            "module": "core",
            "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()
    meta = await ctx.get_meta("SchemaPlanItem")
    assert await preview_sync(meta.doc, engine) == []

    changed = meta.doc.model_copy(deep=True)
    changed.fields.append(DocField(fieldname="rank", label="Rank", fieldtype="Int", index=True))
    invalidate_table_cache("SchemaPlanItem")
    try:
        lines = await preview_sync(changed, engine)
    finally:
        invalidate_table_cache("SchemaPlanItem")
    table = meta.table_name
    assert lines == [f"add column {table}.rank", f"add index ix_{table}_rank"]


@pytest.mark.asyncio
async def test_a_fresh_schema_needs_no_changes(ctx, engine):
    """Every DocType's table, just created, plans nothing - a type the backend
    reflects differently from how it compiles would be ALTERed on every sync."""
    from grunt.metadata.compiler import preview_sync
    from grunt.metadata.registry import doctype_registry

    planned = {}
    tables = [dt for dt in await doctype_registry.list_all() if dt.has_table]
    assert len(tables) > 50  # the core's DocTypes, not a handful
    for dt in tables:
        if lines := await preview_sync(dt, engine):
            planned[dt.name] = lines
    assert planned == {}
