"""Tests for the Meta API — DocType CRUD, sync, and schema export (migrated to
whitelisted methods)."""

from __future__ import annotations

import pytest

SAMPLE_DOCTYPE = {
    "name": "Task",
    "label": "Завдання",
    "module": "core",
    "fields": [
        {
            "fieldname": "title",
            "label": "Назва",
            "fieldtype": "Text",
            "required": True,
            "in_list_view": True,
        },
        {
            "fieldname": "status",
            "label": "Статус",
            "fieldtype": "Select",
            "options": "Draft\nActive\nDone",
            "default": "Draft",
        },
        {"fieldname": "priority", "label": "Пріоритет", "fieldtype": "Int"},
    ],
}


@pytest.mark.asyncio
async def test_doctype_crud_lifecycle(ctx):
    """save → get → list → sync → update → delete → 404, on one DocType."""
    from fastapi import HTTPException

    from grunt.api.v1.meta import (
        delete_doctype,
        get_doctype,
        list_doctypes,
        save_doctype,
        sync_doctype,
    )

    # create
    created = await save_doctype(doctype_data=SAMPLE_DOCTYPE)
    assert created["name"] == "Task"
    assert created["module"] == "core"
    assert len(created["fields"]) == 3

    # get one
    fetched = await get_doctype(name="Task")
    assert fetched["label"] == "Завдання"
    assert {"title", "status", "priority"} <= {f["fieldname"] for f in fetched["fields"]}

    # list
    assert any(item["name"] == "Task" for item in await list_doctypes())

    # sync the physical table
    synced = await sync_doctype(name="Task")
    assert synced["name"] == "Task"
    assert "table_name" in synced

    # update — add a field
    updated = await save_doctype(
        doctype_data={
            **SAMPLE_DOCTYPE,
            "fields": [
                *SAMPLE_DOCTYPE["fields"],
                {"fieldname": "deadline", "label": "Дедлайн", "fieldtype": "Date"},
            ],
        }
    )
    assert len(updated["fields"]) == 4

    # delete → subsequent get 404s
    await delete_doctype(name="Task")
    with pytest.raises(HTTPException) as excinfo:
        await get_doctype(name="Task")
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_doctype_rejected(ctx):
    """Creating a DocType whose name already exists → ApplicationError."""
    from grunt.api.messages import ApplicationError
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data=SAMPLE_DOCTYPE)
    with pytest.raises(ApplicationError) as excinfo:
        await save_doctype(doctype_data={**SAMPLE_DOCTYPE, "__is_new": True})
    assert "already exists" in excinfo.value.message


# ── Schema export ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_schemas_all(ctx):
    """export_schemas() with no filter returns every shipped schema."""
    from grunt.api.v1.meta import export_schemas

    data = await export_schemas()
    assert isinstance(data, dict)
    assert "User" in data
    assert "Role" in data
    assert "fields" in data["User"]


@pytest.mark.asyncio
async def test_export_schemas_filtered(ctx):
    """export_schemas(names=...) restricts the result to the named DocTypes."""
    from grunt.api.v1.meta import export_schemas

    data = await export_schemas(names=["User", "Role"])
    assert set(data.keys()) == {"User", "Role"}


@pytest.mark.asyncio
async def test_export_schemas_module(ctx):
    """export_schemas(module=...) restricts the result to one module."""
    from grunt.api.v1.meta import export_schemas

    # DocType "User" is in module "auth"
    data = await export_schemas(module="auth")
    assert "User" in data
    for dt in data.values():
        assert dt["module"] == "auth"
