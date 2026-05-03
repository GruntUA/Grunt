"""Tests for the Meta API — DocType CRUD and sync (migrated to whitelisted methods)."""

from __future__ import annotations

import pytest

# Direct API tests don't need AsyncClient

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

# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_create_doctype(ctx):
    """POST /method/save_doctype → 200."""
    from grunt.api.v1.meta import save_doctype

    data = await save_doctype(doctype_data=SAMPLE_DOCTYPE)
    assert data["name"] == "Task"
    assert data["module"] == "core"
    assert len(data["fields"]) == 3


@pytest.mark.asyncio
async def test_list_doctypes(ctx):
    """GET /method/list_doctypes → contains created DocType."""
    from grunt.api.v1.meta import list_doctypes, save_doctype

    await save_doctype(doctype_data=SAMPLE_DOCTYPE)
    items = await list_doctypes()
    assert any(item["name"] == "Task" for item in items)


@pytest.mark.asyncio
async def test_get_one_doctype(ctx):
    """GET /method/get_doctype?name=Task → returns correct fields."""
    from grunt.api.v1.meta import get_doctype, save_doctype

    await save_doctype(doctype_data=SAMPLE_DOCTYPE)
    data = await get_doctype(name="Task")
    assert data["name"] == "Task"
    assert data["label"] == "Завдання"
    field_names = [f["fieldname"] for f in data["fields"]]
    assert "title" in field_names
    assert "status" in field_names


@pytest.mark.asyncio
async def test_update_doctype(ctx):
    """POST /method/save_doctype (update) → 200."""
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data=SAMPLE_DOCTYPE)

    updated = {
        **SAMPLE_DOCTYPE,
        "fields": SAMPLE_DOCTYPE["fields"]
        + [
            {"fieldname": "deadline", "label": "Дедлайн", "fieldtype": "Date"},
        ],
    }
    data = await save_doctype(doctype_data=updated)
    assert len(data["fields"]) == 4


@pytest.mark.asyncio
async def test_delete_doctype(ctx):
    """DELETE via /method/delete_doctype → 200, then GET → 404."""
    from fastapi import HTTPException

    from grunt.api.v1.meta import delete_doctype, get_doctype, save_doctype

    await save_doctype(doctype_data=SAMPLE_DOCTYPE)
    await delete_doctype(name="Task")

    with pytest.raises(HTTPException) as excinfo:
        await get_doctype(name="Task")
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_sync_doctype(ctx):
    """POST /method/sync_doctype → 200."""
    from grunt.api.v1.meta import save_doctype, sync_doctype

    await save_doctype(doctype_data=SAMPLE_DOCTYPE)
    data = await sync_doctype(name="Task")
    assert data["name"] == "Task"
    assert "table_name" in data


@pytest.mark.asyncio
async def test_duplicate_doctype_409(ctx):
    """Creating a duplicate DocType → ApplicationError."""
    from grunt.api.messages import ApplicationError
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data=SAMPLE_DOCTYPE)
    with pytest.raises(ApplicationError) as excinfo:
        await save_doctype(doctype_data={**SAMPLE_DOCTYPE, "__is_new": True})
    assert "already exists" in excinfo.value.message
