"""Tests for the DocType Compiler."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from grunt.core.metadata.compiler import (
    SA_METADATA,
    compile_doctype_to_table,
    get_table_name,
    sync_table,
)
from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.field import DocField, FieldType

# ── Fixtures ─────────────────────────────────────────────────────────────


def _make_test_doctype(name: str = "TestDoc", **kwargs) -> DocType:
    """Helper to build a DocType with 8 different field types."""
    fields = [
        DocField(fieldname="title", label="Title", fieldtype=FieldType.TEXT, in_list_view=True),
        DocField(fieldname="description", label="Description", fieldtype=FieldType.LONG_TEXT),
        DocField(fieldname="quantity", label="Quantity", fieldtype=FieldType.INT),
        DocField(fieldname="price", label="Price", fieldtype=FieldType.FLOAT),
        DocField(fieldname="is_active", label="Active", fieldtype=FieldType.BOOL),
        DocField(fieldname="due_date", label="Due Date", fieldtype=FieldType.DATE),
        DocField(
            fieldname="status", label="Status", fieldtype=FieldType.SELECT, options="Draft\nActive"
        ),
        DocField(fieldname="metadata", label="Meta", fieldtype=FieldType.JSON),
        # Non-physical fields — should NOT produce columns
        DocField(fieldname="section_main", label="Main", fieldtype=FieldType.SECTION),
        DocField(fieldname="col_left", label="Left", fieldtype=FieldType.COLUMN),
        DocField(fieldname="tab_details", label="Details", fieldtype=FieldType.TAB),
    ]
    return DocType(name=name, label="Test Document", module="test", fields=fields, **kwargs)


@pytest.fixture
async def async_engine():
    """SQLite in-memory engine for tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    yield engine
    # Clean up SA_METADATA so tables don't leak between tests
    SA_METADATA.clear()
    await engine.dispose()


# ── Tests ────────────────────────────────────────────────────────────────


def test_get_table_name():
    assert get_table_name("crm", "SalesOrder") == "grunt_crm_sales_order"
    assert get_table_name("hr", "Employee") == "grunt_hr_employee"
    assert get_table_name("system", "DocType") == "grunt_system_doc_type"


def test_compile_produces_correct_columns():
    """DocType with 8 field types → table has correct columns."""
    dt = _make_test_doctype()
    table = compile_doctype_to_table(dt)

    col_names = {c.name for c in table.columns}

    # System columns
    for sys_col in ("id", "name", "owner", "created_at", "modified_at", "modified_by", "docstatus"):
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


def test_non_physical_fields_excluded():
    """Section, Column, Tab fields do NOT create database columns."""
    dt = _make_test_doctype()
    table = compile_doctype_to_table(dt)
    col_names = {c.name for c in table.columns}

    for non_phys in ("section_main", "col_left", "tab_details"):
        assert non_phys not in col_names, f"Non-physical field leaked into table: {non_phys}"


def test_child_doctype_has_parent_columns():
    """A child DocType adds parent_id, parent_doctype, parent_field, idx."""
    dt = _make_test_doctype(name="ChildDoc", is_child=True)
    table = compile_doctype_to_table(dt)
    col_names = {c.name for c in table.columns}

    for col in ("parent_id", "parent_doctype", "parent_field", "idx"):
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
    dt.fields.append(DocField(fieldname="extra_col", label="Extra", fieldtype=FieldType.TEXT))
    # Must clear to avoid extend_existing stale cache
    SA_METADATA.remove(SA_METADATA.tables["grunt_test_sync_alter"])
    await sync_table(dt, async_engine)

    async with async_engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("grunt_test_sync_alter")}
        )
    assert "extra_col" in cols
