"""Tests for the Document API — dynamic CRUD for DocType instances (migrated to whitelisted methods)."""

from __future__ import annotations
from typing import TYPE_CHECKING
import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

TEST_DOCTYPE = {
    "name": "TestItem",
    "label": "Test Item",
    "module": "core",
    "fields": [
        {
            "fieldname": "title",
            "label": "Title",
            "fieldtype": "Text",
            "required": True,
            "in_list_view": True,
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "Draft\nActive\nArchived",
            "default": "Draft",
        },
        {"fieldname": "count", "label": "Count", "fieldtype": "Int"},
        {"fieldname": "description", "label": "Description", "fieldtype": "LongText"},
    ],
    "search_fields": ["title"],
}


@pytest.fixture
async def setup_doctype(ctx):
    """Create the TestItem DocType before document tests."""
    from grunt.api.v1.meta import save_doctype
    await save_doctype(doctype_data={**TEST_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_document(ctx, setup_doctype):
    """new_doc → document object with id/name/owner/created_at."""
    doc = await ctx.new_doc("TestItem", {"title": "My First Item", "status": "Draft"})
    await ctx.db._session().commit()

    assert doc["id"]
    assert doc["name"]
    assert doc["owner"] == "system@grunt.local"
    assert doc["created_at"]
    assert doc["title"] == "My First Item"


@pytest.mark.asyncio
async def test_create_without_required_field(ctx, setup_doctype):
    """new_doc without required field → HTTPException."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await ctx.new_doc("TestItem", {"status": "Draft"})
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_list_documents(ctx, setup_doctype):
    """get_list → returns created documents."""
    await ctx.new_doc("TestItem", {"title": "Item A"})
    await ctx.new_doc("TestItem", {"title": "Item B"})
    await ctx.db._session().commit()
    
    body = await ctx.get_list("TestItem")
    assert len(body) == 2


@pytest.mark.asyncio
async def test_list_filter_by_status(ctx, setup_doctype):
    """get_list with filters."""
    await ctx.new_doc("TestItem", {"title": "A", "status": "Draft"})
    await ctx.new_doc("TestItem", {"title": "B", "status": "Active"})
    await ctx.db._session().commit()

    data = await ctx.get_list("TestItem", filters={"status": "Draft"})
    assert len(data) == 1
    assert data[0]["status"] == "Draft"


@pytest.mark.asyncio
async def test_list_search(ctx, setup_doctype):
    """get_list?search=Alpha."""
    await ctx.new_doc("TestItem", {"title": "Alpha Item"})
    await ctx.new_doc("TestItem", {"title": "Beta Item"})
    await ctx.db._session().commit()

    data = await ctx.get_list("TestItem", search="Alpha")
    assert len(data) == 1
    assert "Alpha" in data[0]["title"]


@pytest.mark.asyncio
async def test_list_pagination(ctx, setup_doctype):
    """get_list?page=2&limit=2 (direct call)."""
    from grunt.api.v1.documents import new_doc, get_list
    from grunt.core.doctypes.user.user import SYSTEM_USER
    
    async with ctx.context(ctx.db._session(), ctx._require_engine(), SYSTEM_USER):
        for i in range(5):
            await new_doc("TestItem", {"title": f"Item {i}"})
        await ctx.db._session().commit()

        body = await get_list("TestItem", page=2, limit=2)
        assert body["meta"]["total"] == 5
        assert body["meta"]["page"] == 2
        assert body["meta"]["per_page"] == 2
        assert body["meta"]["pages"] == 3
        assert len(body["data"]) == 2


@pytest.mark.asyncio
async def test_get_document(ctx, setup_doctype):
    """get_doc → returns the document."""
    doc = await ctx.new_doc("TestItem", {"title": "Single Item"})
    await ctx.db._session().commit()
    doc_id = doc["id"]

    retrieved = await ctx.get_doc("TestItem", doc_id)
    assert retrieved["title"] == "Single Item"


@pytest.mark.asyncio
async def test_get_nonexistent_404(ctx, setup_doctype):
    """get_doc nonexistent → HTTPException 404."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await ctx.get_doc("TestItem", "nonexistent")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_document(ctx, setup_doctype):
    """save_doc → modified_at changed."""
    doc = await ctx.new_doc("TestItem", {"title": "Original"})
    await ctx.db._session().commit()
    orig_modified = doc["modified_at"]

    updated = await ctx.save_doc("TestItem", doc["id"], {"title": "Updated"})
    await ctx.db._session().commit()

    assert updated["title"] == "Updated"
    assert updated["modified_at"] != orig_modified


@pytest.mark.asyncio
async def test_delete_document(ctx, setup_doctype):
    """delete_doc → ok, then get_doc → fail."""
    doc = await ctx.new_doc("TestItem", {"title": "ToDelete"})
    await ctx.db._session().commit()
    doc_id = doc["id"]

    await ctx.delete_doc("TestItem", doc_id)
    await ctx.db._session().commit()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await ctx.get_doc("TestItem", doc_id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_partial_fields(ctx, setup_doctype):
    """get_list?fields=["title"] (direct call)."""
    from grunt.api.v1.documents import new_doc, get_list
    from grunt.core.doctypes.user.user import SYSTEM_USER
    
    async with ctx.context(ctx.db._session(), ctx._require_engine(), SYSTEM_USER):
        await new_doc("TestItem", {"title": "Partial", "status": "Active", "count": 42})
        await ctx.db._session().commit()

        body = await get_list("TestItem", fields=["title"])
        row = body["data"][0]
        assert "title" in row
        assert "id" in row  # always included
        assert "name" in row  # always included
        assert "status" not in row
        assert "count" not in row
