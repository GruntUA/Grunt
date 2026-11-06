"""CheckBool - a Check field binds 1 / 0 / "true" as a real bool (PostgreSQL needs it)."""

import pytest
from sqlalchemy import Column, MetaData, String, Table, insert, select, update
from sqlalchemy.ext.asyncio import create_async_engine

from grunt.db.types import CheckBool


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, True),
        (0, False),
        ("1", True),
        ("0", False),
        ("true", True),
        ("False", False),
        ("", False),
        (True, True),
        (None, None),
    ],
)
def test_binds_a_real_bool(value, expected):
    assert CheckBool().process_bind_param(value, None) is expected


def test_compared_values_take_the_column_type():
    t = Table("t", MetaData(), Column("b", CheckBool()))
    clause = (t.c.b == 1).compile()
    assert isinstance(clause.binds["b_1"].type, CheckBool)


@pytest.mark.asyncio
async def test_round_trip_with_int_filters_and_values():
    t = Table("t", MetaData(), Column("name", String, primary_key=True), Column("b", CheckBool()))
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(t.metadata.create_all)
        await conn.execute(insert(t), [{"name": "a", "b": 1}, {"name": "c", "b": "0"}])
        await conn.execute(update(t).where(t.c.name == "c").values(b="true"))
        rows = (await conn.execute(select(t.c.name, t.c.b).where(t.c.b == 1))).all()
    await engine.dispose()
    assert sorted(rows) == [("a", True), ("c", True)]


def test_is_true_renders_a_constant_not_a_parameter():
    from sqlalchemy.dialects import postgresql

    t = Table("t", MetaData(), Column("b", CheckBool()))
    pg = postgresql.dialect()
    # "IS $1" is a syntax error on PostgreSQL
    assert str(t.c.b.is_(True).compile(dialect=pg)) == "t.b IS true"
    assert str(t.c.b.is_not(False).compile(dialect=pg)) == "t.b IS NOT false"
    assert str(t.c.b.is_(None).compile(dialect=pg)) == "t.b IS NULL"
