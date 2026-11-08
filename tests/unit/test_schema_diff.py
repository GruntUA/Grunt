"""``grunt.db.schema.diff`` - the plan for a table, worked out without a database."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from grunt.db.schema import (
    Actual,
    AddColumn,
    AddIndex,
    AddUnique,
    AlterType,
    CreateTable,
    DropColumn,
    DropIndex,
    DropUnique,
    describe,
    diff,
    read_actual,
)

PG = postgresql.dialect()
LITE = sqlite.dialect()


def _desired() -> sa.Table:
    meta = sa.MetaData()
    status = sa.Column("status", sa.String(140))
    status.info["backfill_default"] = "Open"
    return sa.Table(
        "grunt_test_item",
        meta,
        sa.Column("name", sa.String(255), primary_key=True),
        status,
        sa.Column("qty", sa.Integer),
        sa.Column("code", sa.String(140)),
        sa.UniqueConstraint("code", name="uq_grunt_test_item_code"),
        sa.Index("ix_grunt_test_item_status", "status"),
    )


def _actual(**over) -> Actual:
    base = {
        "columns": {
            "name": sa.VARCHAR(255),
            "status": sa.VARCHAR(140),
            "qty": sa.INTEGER(),
            "code": sa.VARCHAR(140),
        },
        "uniques": {},
        "unique_indexes": {"uq_grunt_test_item_code": ("code",)},
        "indexes": {"ix_grunt_test_item_status": ("status",)},
    }
    return Actual(**{**base, **over})


def _plan(actual, **kw):
    kw.setdefault("sa_dialect", PG)
    kw.setdefault("can_alter_type", True)
    return diff(_desired(), actual, **kw)


def test_no_table_is_created():
    [change] = _plan(None)
    assert isinstance(change, CreateTable)


def test_in_sync_needs_nothing():
    assert _plan(_actual()) == []


def test_a_new_column_is_added_with_its_backfill():
    actual = _actual(columns={"name": sa.VARCHAR(255), "qty": sa.INTEGER(), "code": sa.VARCHAR()})
    [change] = _plan(actual)
    assert isinstance(change, AddColumn)
    assert change.column.name == "status"
    assert change.backfill == "Open"


def test_a_type_change_alters_or_rebuilds():
    columns = {**_actual().columns, "qty": sa.VARCHAR(140)}
    [alter] = _plan(_actual(columns=columns))
    assert isinstance(alter, AlterType) and not alter.rebuild

    [rebuild] = _plan(_actual(columns=columns), sa_dialect=LITE, can_alter_type=False)
    assert isinstance(rebuild, AlterType) and rebuild.rebuild
    assert "rebuild the table" in rebuild.describe()


def test_reflected_aliases_are_not_a_change():
    columns = {**_actual().columns, "qty": sa.BIGINT()}
    assert _plan(_actual(columns=columns)) == []


def test_uniques_are_added_and_stale_ones_dropped():
    [add] = _plan(_actual(unique_indexes={}))
    assert isinstance(add, AddUnique)
    assert (add.name, add.columns) == ("uq_grunt_test_item_code", ("code",))

    stale = {"uq_grunt_test_item_code": ("code",), "uq_grunt_test_item_old": ("old",)}
    [drop] = _plan(_actual(unique_indexes=stale))
    assert isinstance(drop, DropUnique) and drop.name == "uq_grunt_test_item_old"
    assert drop.is_index

    inline = _plan(_actual(uniques={"uq_grunt_test_item_old": ("old",)}))
    assert [(type(c), c.is_index) for c in inline] == [(DropUnique, False)]

    # someone else's unique (no prefix of ours) is left alone
    foreign = {"uq_grunt_test_item_code": ("code",), "custom_unique": ("x",)}
    assert _plan(_actual(unique_indexes=foreign)) == []


def test_indexes_are_added_and_stale_ones_dropped_only_when_asked():
    [add] = _plan(_actual(indexes={}))
    assert isinstance(add, AddIndex) and add.index.name == "ix_grunt_test_item_status"

    stale = {"ix_grunt_test_item_status": ("status",), "ix_grunt_test_item_old": ("qty",)}
    assert _plan(_actual(indexes=stale)) == []
    [drop] = _plan(_actual(indexes=stale), drop_indexes=True)
    assert drop == DropIndex(drop.table, "ix_grunt_test_item_old")

    # another DocType on the same table still wants it
    assert _plan(_actual(indexes=stale), drop_indexes=True, keep={"ix_grunt_test_item_old"}) == []
    # not ours
    other = {"ix_grunt_test_item_status": ("status",), "custom_ix": ("qty",)}
    assert _plan(_actual(indexes=other), drop_indexes=True) == []


def test_columns_are_dropped_only_when_asked_with_their_indexes():
    columns = {**_actual().columns, "legacy": sa.VARCHAR(140)}
    indexes = {"ix_grunt_test_item_status": ("status",), "ix_legacy": ("legacy", "qty")}
    actual = _actual(columns=columns, indexes=indexes)
    assert _plan(actual) == []

    [drop] = _plan(actual, drop_columns=True)
    assert isinstance(drop, DropColumn)
    assert drop.name == "legacy" and drop.indexes == ("ix_legacy",)

    assert _plan(actual, drop_columns=True, keep={"legacy"}) == []


def test_describe_reads_as_a_plan():
    columns = {"name": sa.VARCHAR(255), "qty": sa.VARCHAR(10), "code": sa.VARCHAR(140)}
    lines = describe(_plan(_actual(columns=columns, indexes={})))
    assert lines == [
        "add column grunt_test_item.status",
        "change type of grunt_test_item.qty: VARCHAR -> INTEGER",
        "add index ix_grunt_test_item_status",
    ]


def test_read_actual_reflects_a_real_table():
    engine = sa.create_engine("sqlite://")
    table = _desired()
    with engine.begin() as conn:
        assert read_actual(conn, table.name) is None
        table.metadata.create_all(conn)
        actual = read_actual(conn, table.name)
        assert actual is not None
        assert set(actual.columns) == {"name", "status", "qty", "code"}
        assert actual.indexes == {"ix_grunt_test_item_status": ("status",)}
        assert diff(table, actual, sa_dialect=LITE, can_alter_type=False) == []
    engine.dispose()


def test_postgres_timestamps_with_a_zone_are_not_a_change():
    """PostgreSQL compiles ``TIMESTAMP WITH TIME ZONE`` and reflects
    ``TIMESTAMP(timezone=True)`` - the same column (it was ALTERed on every sync)."""
    from sqlalchemy.dialects.postgresql import TIMESTAMP

    from grunt.db.schema.diff import type_changed
    from grunt.db.types import UtcDateTime

    assert not type_changed(UtcDateTime(), TIMESTAMP(timezone=True), PG)
    assert type_changed(UtcDateTime(), TIMESTAMP(timezone=False), PG)  # a naive column is
    assert not type_changed(UtcDateTime(), sa.DATETIME(), LITE)


def test_an_index_held_twice_is_added_once():
    """A Table compiled again into the same MetaData (``extend_existing``) holds
    each Index twice - one CREATE INDEX, not two (the second would fail)."""
    table = _desired()
    sa.Table(
        table.name,
        table.metadata,
        sa.Index("ix_grunt_test_item_status", "status"),
        extend_existing=True,
    )
    assert len([i for i in table.indexes if i.name == "ix_grunt_test_item_status"]) == 2
    adds = [c for c in _plan(_actual(indexes={})) if isinstance(c, AddIndex)]
    plan = diff(table, _actual(indexes={}), sa_dialect=PG, can_alter_type=True)
    assert [c.index.name for c in plan if isinstance(c, AddIndex)] == ["ix_grunt_test_item_status"]
    assert len(adds) == 1
