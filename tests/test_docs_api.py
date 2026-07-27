"""Tests for the Document API — dynamic CRUD for DocType instances."""

from __future__ import annotations

import pytest

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

    assert doc["name"]
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
    from grunt.api.v1.documents import get_list, new_doc
    from grunt.auth.doctypes.User.user import SYSTEM_USER

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
async def test_list_cursor_pagination(ctx, setup_doctype):
    """cursor pagination: next_cursor returned on page 1, used on page 2, no overlap."""
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    session = ctx.db._session()
    engine = ctx._require_engine()

    async with ctx.context(session, engine, SYSTEM_USER):
        for i in range(5):
            await ctx.new_doc("TestItem", {"title": f"Cursor {i}"})
        await session.commit()

        # Page 1 via cursor mode (limit=2)
        page1 = await ctx.get_list("TestItem", limit=2, order_by="modified_at", order="desc")
        assert len(page1) == 2
        cursor = page1.meta.get("next_cursor")
        assert cursor is not None, "next_cursor must be set when a full page is returned"

        # Page 2 via cursor — must not overlap with page 1
        page2 = await ctx.get_list(
            "TestItem", limit=2, order_by="modified_at", order="desc", cursor=cursor
        )
        assert len(page2) == 2
        ids1 = {r["name"] for r in page1}
        ids2 = {r["name"] for r in page2}
        assert ids1.isdisjoint(ids2), "cursor pages must not overlap"

        # Page 3 (only 1 remaining) — next_cursor should be None
        cursor2 = page2.meta.get("next_cursor")
        assert cursor2 is not None
        page3 = await ctx.get_list(
            "TestItem", limit=2, order_by="modified_at", order="desc", cursor=cursor2
        )
        assert len(page3) == 1
        assert page3.meta.get("next_cursor") is None


@pytest.mark.asyncio
async def test_get_list_query_cache_read_only_invalidation(ctx):
    """Read-only DocType lists are cached and invalidated on write."""
    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            "name": "CacheReadOnlyItem",
            "label": "Cache ReadOnly Item",
            "module": "core",
            "fields": [
                {
                    "fieldname": "title",
                    "label": "Title",
                    "fieldtype": "Text",
                    "required": True,
                },
            ],
            "permissions": [
                {
                    "role": "System Manager",
                    "read": True,
                    "write": False,
                    "create": False,
                    "delete": False,
                    "submit": False,
                    "report": True,
                }
            ],
            "search_fields": ["title"],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    first = await ctx.new_doc("CacheReadOnlyItem", {"title": "Cached A"})
    await ctx.new_doc("CacheReadOnlyItem", {"title": "Cached B"})
    await ctx.db._session().commit()

    ctx.query_cache.clear()
    s0 = ctx.query_cache.stats()

    await ctx.get_list("CacheReadOnlyItem", limit=10)
    s1 = ctx.query_cache.stats()
    assert s1["misses"] == s0["misses"] + 1

    await ctx.get_list("CacheReadOnlyItem", limit=10)
    s2 = ctx.query_cache.stats()
    assert s2["hits"] == s1["hits"] + 1
    assert s2["keys"] >= 1

    await ctx.save_doc("CacheReadOnlyItem", first["name"], {"title": "Cached A+"})
    await ctx.db._session().commit()
    assert ctx.query_cache.stats()["keys"] == 0


@pytest.mark.asyncio
async def test_dev_query_cache_methods(ctx, setup_doctype):
    """Dev methods expose and clear query cache stats."""
    from grunt.api.v1.dev import clear_query_cache, get_query_cache_stats

    await ctx.new_doc("TestItem", {"title": "A"})
    await ctx.new_doc("TestItem", {"title": "B"})
    await ctx.db._session().commit()

    await clear_query_cache()
    stats0 = await get_query_cache_stats()
    assert stats0["keys"] == 0

    await ctx.get_list("TestItem", limit=10)
    stats1 = await get_query_cache_stats()
    assert "hits" in stats1
    assert "misses" in stats1
    assert "keys" in stats1


@pytest.mark.asyncio
async def test_get_document(ctx, setup_doctype):
    """get_doc → returns the document."""
    doc = await ctx.new_doc("TestItem", {"title": "Single Item"})
    await ctx.db._session().commit()
    doc_id = doc["name"]

    retrieved = await ctx.get_doc("TestItem", doc_id)
    assert retrieved["title"] == "Single Item"


@pytest.mark.asyncio
async def test_get_document_expand_multilink(ctx):
    """expand controls MultiLink loading for get_document."""
    from grunt.api.v1.meta import save_doctype
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    await save_doctype(
        doctype_data={
            "name": "ExpandItem",
            "label": "Expand Item",
            "module": "core",
            "fields": [
                {
                    "fieldname": "title",
                    "label": "Title",
                    "fieldtype": "Text",
                    "required": True,
                },
                {
                    "fieldname": "watchers",
                    "label": "Watchers",
                    "fieldtype": "MultiLink",
                    "options": "User",
                },
            ],
            "search_fields": ["title"],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    created = await ctx.new_doc(
        "ExpandItem",
        {"title": "Has Watchers", "watchers": ["system@grunt.local"]},
    )
    await ctx.db._session().commit()

    session = ctx.db._session()
    engine = ctx._require_engine()

    async with ctx.context(session, engine, SYSTEM_USER):
        full_doc = await ctx.get_doc("ExpandItem", created["name"])
        assert "watchers" in full_doc
        assert full_doc["watchers"] == ["system@grunt.local"]

        narrow_doc = await ctx.get_doc("ExpandItem", created["name"], expand=["title"])
        assert "watchers" not in narrow_doc

        expanded_doc = await ctx.get_doc("ExpandItem", created["name"], expand=["watchers"])
        assert expanded_doc["watchers"] == ["system@grunt.local"]


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

    updated = await ctx.save_doc("TestItem", doc["name"], {"title": "Updated"})
    await ctx.db._session().commit()

    assert updated["title"] == "Updated"
    assert updated["modified_at"] != orig_modified


@pytest.mark.asyncio
async def test_delete_document(ctx, setup_doctype):
    """delete_doc → ok, then get_doc → fail."""
    doc = await ctx.new_doc("TestItem", {"title": "ToDelete"})
    await ctx.db._session().commit()
    doc_id = doc["name"]

    await ctx.delete_doc("TestItem", doc_id)
    await ctx.db._session().commit()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await ctx.get_doc("TestItem", doc_id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_aggregate_count_without_filters(ctx, setup_doctype):
    """aggregate count with no filters/group_by must still count table rows.

    Regression: a bare select(func.count()) has no FROM clause, so SQLite
    returned 1 regardless of row count until select_from(table) was forced.
    """
    for i in range(3):
        await ctx.new_doc("TestItem", {"title": f"Item {i}"})
    await ctx.db._session().commit()

    rows = await ctx.db.aggregate("TestItem", aggregations={"val": "count"})
    assert rows[0]["val"] == 3


@pytest.mark.asyncio
async def test_bulk_delete_documents(ctx, setup_doctype):
    """bulk_delete_docs removes multiple docs and reports missing IDs."""
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    a = await ctx.new_doc("TestItem", {"title": "Bulk A"})
    b = await ctx.new_doc("TestItem", {"title": "Bulk B"})
    await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx._require_engine(), SYSTEM_USER):
        deleted, errors = await ctx.bulk_delete_docs(
            "TestItem",
            [a["name"], b["name"], "missing-id"],
        )
        await ctx.db._session().commit()

    assert deleted == 2
    assert len(errors) == 1
    assert errors[0].startswith("missing-id:")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_a:
        await ctx.get_doc("TestItem", a["name"])
    assert exc_a.value.status_code == 404

    with pytest.raises(HTTPException) as exc_b:
        await ctx.get_doc("TestItem", b["name"])
    assert exc_b.value.status_code == 404


@pytest.mark.asyncio
async def test_list_partial_fields(ctx, setup_doctype):
    """get_list?fields=["title"] (direct call)."""
    from grunt.api.v1.documents import get_list, new_doc
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    async with ctx.context(ctx.db._session(), ctx._require_engine(), SYSTEM_USER):
        await new_doc("TestItem", {"title": "Partial", "status": "Active", "count": 42})
        await ctx.db._session().commit()

        body = await get_list("TestItem", fields=["title"])
        row = body["data"][0]
        assert "title" in row
        assert "name" in row  # always included
        assert "name" in row  # always included
        assert "status" not in row
        assert "count" not in row


@pytest.mark.asyncio
async def test_link_search_returns_compact_items(ctx, setup_doctype):
    """link_search should return compact rows and honor title/search fields."""
    from grunt.api.v1.docs.link import link_search
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    await ctx.new_doc("TestItem", {"title": "Alpha Item", "status": "Draft"})
    await ctx.new_doc("TestItem", {"title": "Beta Item", "status": "Active"})
    await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx._require_engine(), SYSTEM_USER):
        body = await link_search(
            "TestItem",
            q="Alpha",
            filters='{"status": "Draft"}',
            page_length=10,
            user=SYSTEM_USER,
        )

    assert body["success"] is True
    items = body["data"]
    assert len(items) == 1
    assert items[0]["title"] == "Alpha Item"
    assert items[0]["subtitle"] == items[0]["name"]
