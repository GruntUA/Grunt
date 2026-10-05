"""Tests for the DocType Compiler."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from grunt.metadata.compiler import (
    MULTI_LINK_TABLE,
    compile_doctype_to_table,
    get_compiled_metadata,
    get_table_name,
    invalidate_table_cache,
    sync_table,
)
from grunt.metadata.doctype import DocType
from grunt.metadata.field import DocField

# ── Fixtures ─────────────────────────────────────────────────────────────


def _make_test_doctype(name: str = "TestDoc", **kwargs) -> DocType:
    """Helper to build a DocType with 8 different field types."""
    fields = [
        DocField(fieldname="title", label="Title", fieldtype="Text", in_list_view=True),
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
    for sys_col in ("name", "owner", "created_at", "modified_at", "modified_by", "docstatus"):
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
    dt.fields.append(DocField(fieldname="extra_col", label="Extra", fieldtype="Text"))
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
        DocField(fieldname="note", label="Note", fieldtype="Text", default="hi"),
        DocField(fieldname="since", label="Since", fieldtype="Date", default="Today"),
        DocField(fieldname="plain", label="Plain", fieldtype="Text"),
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

    from grunt.metadata.compiler import _type_changed

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
