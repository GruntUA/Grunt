"""Tests for the DocType Compiler."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from grunt.metadata.compiler import (
    MULTI_LINK_TABLE,
    compile_doctype_to_table,
    get_compiled_metadata,
    get_table_name,
    index_name,
    invalidate_table_cache,
    plan_sync,
    sync_table,
)
from grunt.metadata.doctype import DocType
from grunt.metadata.field import DocField

# ── Fixtures ─────────────────────────────────────────────────────────────


def _make_test_doctype(name: str = "TestDoc", **kwargs) -> DocType:
    """Helper to build a DocType with 8 different field types."""
    fields = [
        DocField(fieldname="title", label="Title", fieldtype="Data", in_list_view=True),
        DocField(fieldname="description", label="Description", fieldtype="LongText"),
        DocField(fieldname="quantity", label="Quantity", fieldtype="Int"),
        DocField(fieldname="price", label="Price", fieldtype="Float"),
        DocField(fieldname="is_active", label="Active", fieldtype="Check"),
        DocField(fieldname="due_date", label="Due Date", fieldtype="Date"),
        DocField(fieldname="status", label="Status", fieldtype="Select", options="Draft\nActive"),
        DocField(fieldname="metadata", label="Meta", fieldtype="JSON"),
        # Non-physical fields — should NOT produce columns
        DocField(fieldname="section_main", label="Main", fieldtype="Section"),
        DocField(fieldname="col_left", label="Left", fieldtype="Column"),
        DocField(fieldname="tab_details", label="Details", fieldtype="Tab"),
    ]
    return DocType(name=name, label="Test Document", module="test", fields=fields, **kwargs)


@pytest.fixture
async def async_engine():
    """SQLite in-memory engine for tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    yield engine
    # Clean up the compiled-table metadata so tables don't leak between tests
    get_compiled_metadata().clear()
    await engine.dispose()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_table_name():
    assert get_table_name("crm", "SalesOrder") == "grunt_crm_sales_order"
    assert get_table_name("hr", "Employee") == "grunt_hr_employee"
    assert get_table_name("system", "DocType") == "grunt_system_doc_type"


@pytest.mark.asyncio
async def test_compile_produces_correct_columns():
    """DocType with 8 field types → table has correct columns."""
    dt = _make_test_doctype()
    table = compile_doctype_to_table(dt)

    col_names = {c.name for c in table.columns}

    # System columns
    for sys_col in ("name", "owner", "created_at", "modified_at", "modified_by"):
        assert sys_col in col_names, f"Missing system column: {sys_col}"

    # User-defined physical columns
    for expected in (
        "title",
        "description",
        "quantity",
        "price",
        "is_active",
        "due_date",
        "status",
        "metadata",
    ):
        assert expected in col_names, f"Missing field column: {expected}"


@pytest.mark.asyncio
async def test_non_physical_fields_excluded():
    """Section, Column, Tab fields do NOT create database columns."""
    dt = _make_test_doctype()
    table = compile_doctype_to_table(dt)
    col_names = {c.name for c in table.columns}

    for non_phys in ("section_main", "col_left", "tab_details"):
        assert non_phys not in col_names, f"Non-physical field leaked into table: {non_phys}"


@pytest.mark.asyncio
async def test_child_doctype_has_parent_columns():
    """A child DocType adds parent_id, parent_doctype, parent_field, idx."""
    dt = _make_test_doctype(name="ChildDoc", is_child=True)
    table = compile_doctype_to_table(dt)
    col_names = {c.name for c in table.columns}

    for col in ("parent_name", "parent_doctype", "parent_field", "idx"):
        assert col in col_names


@pytest.mark.asyncio
async def test_sync_table_creates_table(async_engine):
    """sync_table creates the table when it does not exist."""
    dt = _make_test_doctype(name="SyncCreate")
    await sync_table(dt, async_engine)

    async with async_engine.connect() as conn:
        result = await conn.run_sync(lambda c: inspect(c).has_table("grunt_test_sync_create"))
    assert result is True


@pytest.mark.asyncio
async def test_sync_table_idempotent(async_engine):
    """Calling sync_table twice does not raise."""
    dt = _make_test_doctype(name="SyncIdem")
    await sync_table(dt, async_engine)
    await sync_table(dt, async_engine)  # second call — must not fail

    async with async_engine.connect() as conn:
        result = await conn.run_sync(lambda c: inspect(c).has_table("grunt_test_sync_idem"))
    assert result is True


@pytest.mark.asyncio
async def test_sync_table_adds_new_column(async_engine):
    """When a new field is added, sync_table adds the column via ALTER TABLE."""
    dt = _make_test_doctype(name="SyncAlter")
    await sync_table(dt, async_engine)

    # Add a new field
    dt.fields.append(DocField(fieldname="extra_col", label="Extra", fieldtype="Data"))
    # Must clear both the compiled Table object and the compile cache so
    # sync_table rebuilds the Table with the new column.
    compiled_metadata = get_compiled_metadata()
    compiled_metadata.remove(compiled_metadata.tables["grunt_test_sync_alter"])
    invalidate_table_cache("SyncAlter")
    await sync_table(dt, async_engine)

    async with async_engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("grunt_test_sync_alter")}
        )
    assert "extra_col" in cols


@pytest.mark.asyncio
async def test_new_column_backfills_static_default(async_engine):
    """Existing rows get a new field's static default, as a new document would."""
    from sqlalchemy import text

    dt = _make_test_doctype(name="SyncBackfill")
    await sync_table(dt, async_engine)
    async with async_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO grunt_test_sync_backfill (name, owner) VALUES ('a', 'x')")
        )

    dt.fields += [
        DocField(fieldname="enabled", label="On", fieldtype="Check", default=1),
        DocField(fieldname="term", label="Term", fieldtype="Int", default="30"),
        DocField(fieldname="note", label="Note", fieldtype="Data", default="hi"),
        DocField(fieldname="since", label="Since", fieldtype="Date", default="Today"),
        DocField(fieldname="plain", label="Plain", fieldtype="Data"),
    ]
    compiled_metadata = get_compiled_metadata()
    compiled_metadata.remove(compiled_metadata.tables["grunt_test_sync_backfill"])
    invalidate_table_cache("SyncBackfill")
    await sync_table(dt, async_engine)

    async with async_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT enabled, term, note, since, plain FROM grunt_test_sync_backfill")
            )
        ).one()
    assert tuple(row) == (1, 30, "hi", None, None)


def test_multi_link_table_has_query_supporting_index_and_unique_order_constraint():
    """MultiLink table should enforce deterministic order and support read/delete queries."""
    index_names = {index.name for index in MULTI_LINK_TABLE.indexes}
    assert "ix_grunt_core_multi_link_parent_parentfield_idx" in index_names

    # Composite PK (parent_doctype, parent_name, parent_field, idx) enforces uniqueness.
    pk_cols = {c.name for c in MULTI_LINK_TABLE.primary_key.columns}
    assert pk_cols == {"parent_doctype", "parent_name", "parent_field", "idx"}


def test_float_is_double_and_currency_is_exact_numeric():
    from sqlalchemy import Double, Numeric
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, NUMERIC, REAL

    from grunt.db.schema.diff import type_changed as _type_changed

    flt = DocField(fieldname="f", label="F", fieldtype="Float").to_sa_column().type
    cur = DocField(fieldname="c", label="C", fieldtype="Currency")
    assert isinstance(flt, Double)
    assert isinstance(cur.to_sa_column().type, Numeric)
    assert cur.coerce("12.345") == 12.35

    pg = postgresql.dialect()
    assert _type_changed(flt, REAL(), pg)  # legacy 4-byte column gets widened
    assert not _type_changed(flt, DOUBLE_PRECISION(), pg)
    assert _type_changed(cur.to_sa_column().type, DOUBLE_PRECISION(), pg)  # Float → Currency
    assert not _type_changed(cur.to_sa_column().type, NUMERIC(18, 2), pg)


@pytest.mark.asyncio
async def test_sqlite_inline_unique_dropped_by_table_rebuild(async_engine):
    """A unique field turned off drops its constraint even when SQLite declared it
    inline in CREATE TABLE - the table is rebuilt, rows, other constraints and
    indexes kept."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    dt = DocType(
        name="InlineUq",
        label="Inline",
        module="test",
        fields=[
            DocField(fieldname="title", label="Title", fieldtype="Data", unique=True),
            DocField(fieldname="route", label="Route", fieldtype="Data", unique=True),
            DocField(fieldname="kind", label="Kind", fieldtype="Data", index=True),
        ],
    )
    await sync_table(dt, async_engine)
    async with async_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO grunt_test_inline_uq (name, owner, title, route, kind) "
                "VALUES ('a', 'x', 'T', 'r1', 'k')"
            )
        )

    dt.fields[0].unique = False
    compiled_metadata = get_compiled_metadata()
    compiled_metadata.remove(compiled_metadata.tables["grunt_test_inline_uq"])
    invalidate_table_cache("InlineUq")
    assert await sync_table(dt, async_engine)

    async with async_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO grunt_test_inline_uq (name, owner, title, route) "
                "VALUES ('b', 'x', 'T', 'r2')"
            )
        )
        rows = (await conn.execute(text("SELECT name, kind FROM grunt_test_inline_uq"))).all()
        indexes = await conn.run_sync(
            lambda c: {ix["name"] for ix in inspect(c).get_indexes("grunt_test_inline_uq")}
        )
    assert sorted(rows) == [("a", "k"), ("b", None)]
    assert any("kind" in name for name in indexes)

    with pytest.raises(IntegrityError):
        async with async_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO grunt_test_inline_uq (name, owner, title, route) "
                    "VALUES ('c', 'x', 'U', 'r1')"
                )
            )


# ── Implicit indexes ─────────────────────────────────────────────────────


def _index_columns(table) -> dict[str, tuple[str, ...]]:
    return {str(ix.name): tuple(c.name for c in ix.columns) for ix in table.indexes}


def test_link_fields_and_modified_at_are_indexed():
    dt = DocType(
        name="IxOrder",
        label="Order",
        module="test",
        fields=[
            DocField(fieldname="customer", label="Customer", fieldtype="Link", options="Customer"),
            DocField(fieldname="title", label="Title", fieldtype="Data"),
        ],
    )
    indexes = _index_columns(compile_doctype_to_table(dt))
    assert indexes["ix_grunt_test_ix_order_customer"] == ("customer",)
    assert indexes["ix_grunt_test_ix_order_modified_at"] == ("modified_at",)
    assert not any("title" in cols for cols in indexes.values())


def test_child_table_indexes_parent_name_not_modified_at():
    dt = DocType(name="IxRow", label="Row", module="test", is_child=True, fields=[])
    indexes = _index_columns(compile_doctype_to_table(dt))
    assert ("parent_name",) in indexes.values()
    assert ("modified_at",) not in indexes.values()


def test_dynamic_link_gets_one_composite_index():
    dt = DocType(
        name="IxNote",
        label="Note",
        module="test",
        fields=[
            DocField(fieldname="ref_doctype", label="Type", fieldtype="Link", options="DocType"),
            DocField(
                fieldname="ref_name", label="Doc", fieldtype="DynamicLink", options="ref_doctype"
            ),
        ],
    )
    indexes = _index_columns(compile_doctype_to_table(dt))
    assert indexes["ix_grunt_test_ix_note_ref_doctype_ref_name"] == ("ref_doctype", "ref_name")
    # The composite already leads with ref_doctype - no lone index on it.
    assert ("ref_doctype",) not in indexes.values()


def test_already_indexed_columns_get_no_second_index():
    dt = DocType(
        name="IxDup",
        label="Dup",
        module="test",
        indexes=[["owner_link", "title"]],
        fields=[
            DocField(fieldname="code", label="Code", fieldtype="Link", options="X", unique=True),
            DocField(fieldname="owner_link", label="O", fieldtype="Link", options="User"),
            DocField(fieldname="title", label="Title", fieldtype="Data"),
            DocField(fieldname="virt", label="V", fieldtype="Link", options="X", is_virtual=True),
        ],
    )
    indexes = _index_columns(compile_doctype_to_table(dt))
    assert ("code",) not in indexes.values()
    assert ("owner_link",) not in indexes.values()
    assert ("owner_link", "title") in indexes.values()
    assert not any("virt" in cols for cols in indexes.values())


def test_index_name_fits_postgres_identifier_limit():
    short = index_name("grunt_test_doc", "customer")
    assert short == "ix_grunt_test_doc_customer"
    long = index_name("grunt_inventory_crystal_finance_holding_history", "counterparty_account")
    assert len(long) == 63
    assert long.startswith("ix_grunt_inventory_crystal_finance_holding")
    assert long != index_name(
        "grunt_inventory_crystal_finance_holding_history", "counterparty_acc0"
    )
    # PostgreSQL's limit is in bytes - Cyrillic takes two per letter.
    cyrillic = index_name("grunt_test_таблиця_документів", "поле_звʼязку_з_контрагентом")
    assert len(cyrillic.encode()) <= 63


@pytest.mark.asyncio
async def test_implicit_indexes_are_created_and_stable(async_engine):
    dt = DocType(
        name="IxSync",
        label="Sync",
        module="test",
        fields=[DocField(fieldname="customer", label="C", fieldtype="Link", options="Customer")],
    )
    await sync_table(dt, async_engine)
    async with async_engine.connect() as conn:
        names = await conn.run_sync(
            lambda c: {ix["name"] for ix in inspect(c).get_indexes("grunt_test_ix_sync")}
        )
        table = compile_doctype_to_table(dt)
        again = await conn.run_sync(lambda c: plan_sync(c, table))
    assert {"ix_grunt_test_ix_sync_customer", "ix_grunt_test_ix_sync_modified_at"} <= names
    assert again == []
