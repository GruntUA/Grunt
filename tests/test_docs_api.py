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
async def test_list_search_by_link_field_title(ctx, setup_doctype):
    """get_list?search=<linked doc's title> should match through a Link field,
    not just the raw id it stores."""
    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            "name": "TestOwner",
            "label": "Test Owner",
            "module": "core",
            "fields": [{"fieldname": "full_name", "label": "Full Name", "fieldtype": "Data"}],
            "title_field": "full_name",
            "__is_new": True,
        }
    )
    await save_doctype(
        doctype_data={
            "name": "TestAsset",
            "label": "Test Asset",
            "module": "core",
            "fields": [
                {"fieldname": "asset_name", "label": "Asset Name", "fieldtype": "Data"},
                {
                    "fieldname": "owner_link",
                    "label": "Owner",
                    "fieldtype": "Link",
                    "options": "TestOwner",
                },
            ],
            "search_fields": ["asset_name", "owner_link"],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    owner = await ctx.new_doc("TestOwner", {"full_name": "Сисоєнко Іван"})
    await ctx.new_doc("TestAsset", {"asset_name": "Ноутбук", "owner_link": owner["name"]})
    await ctx.new_doc("TestAsset", {"asset_name": "Монітор"})
    await ctx.db._session().commit()

    data = await ctx.get_list("TestAsset", search="Сисо")
    assert len(data) == 1
    assert data[0]["asset_name"] == "Ноутбук"


@pytest.mark.asyncio
async def test_list_pagination(ctx, setup_doctype):
    """get_list?page=2&limit=2 (direct call)."""
    from grunt.api.v1.documents import get_list, new_doc
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    async with ctx.context(ctx.db._session(), ctx.get_engine(), SYSTEM_USER):
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
    engine = ctx.get_engine()

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
    engine = ctx.get_engine()

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
async def test_direct_insert_fires_same_hooks_as_facade(ctx, setup_doctype):
    """Document.insert()/.save()/.delete() must fire hooks.fire events, not just grunt_app.*.

    Regression: hooks.fire() used to live only in the app/document_api.py facade,
    so a controller or background task calling doc.insert()/.save()/.delete()
    directly silently skipped notifications/assignment rules/backlink sync/
    activity log. hooks.fire() now lives inside create_document/update_document/
    delete_document (grunt/document/mixins/write.py) so every entry point gets
    the same guarantees.
    """
    from grunt import hooks
    from grunt.document.base import Document

    fired: list[str] = []

    async def _capture(**kwargs):
        fired.append(kwargs["event"])

    for event in ("after_insert", "after_update", "after_delete"):
        hooks.on_doc("TestItem", event)(_capture)

    try:
        doc = Document("TestItem", {"title": "Direct pipeline"})
        await doc.insert()
        await ctx.db._session().commit()

        doc.title = "Direct pipeline updated"
        await doc.save()
        await ctx.db._session().commit()

        await doc.delete()
        await ctx.db._session().commit()
    finally:
        for event in ("after_insert", "after_update", "after_delete"):
            hooks.DOC_EVENT_REGISTRY["TestItem"][event] = [
                h
                for h in hooks.DOC_EVENT_REGISTRY["TestItem"][event]
                if h["handler"] is not _capture
            ]

    assert fired == ["after_insert", "after_update", "after_delete"]


@pytest.mark.asyncio
async def test_explicit_name_wins_over_autoname(ctx, setup_doctype):
    """new_doc with explicit ``name`` keeps it even when autoname is hash.

    Regression: fixtures with explicit names silently got hash names
    (autoname empty → hash fallback ignored data["name"]), so every
    re-apply created a duplicate under a new hash.
    """
    doc = await ctx.new_doc("TestItem", {"name": "fixed-name", "title": "Named"})
    await ctx.db._session().commit()
    assert doc["name"] == "fixed-name"

    fetched = await ctx.get_doc("TestItem", "fixed-name")
    assert fetched["title"] == "Named"


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
async def test_aggregate_group_by_with_sum_and_order_by(ctx, setup_doctype):
    """group_by + sum() + order_by resolved against the labeled select, not raw SQL."""
    await ctx.new_doc("TestItem", {"title": "A1", "status": "Draft", "count": 10})
    await ctx.new_doc("TestItem", {"title": "A2", "status": "Draft", "count": 5})
    await ctx.new_doc("TestItem", {"title": "B1", "status": "Active", "count": 100})
    await ctx.db._session().commit()

    rows = await ctx.db.aggregate(
        "TestItem",
        group_by="status",
        aggregations={"total": "sum(count)"},
        order_by="total",
        order="desc",
    )
    assert [(r["status"], r["total"]) for r in rows] == [("Active", 100), ("Draft", 15)]


@pytest.mark.asyncio
async def test_aggregate_group_by_date_expr(ctx, setup_doctype):
    """group_by="date(created_at)" groups by calendar day, not full timestamp."""
    await ctx.new_doc("TestItem", {"title": "A1", "status": "Draft"})
    await ctx.new_doc("TestItem", {"title": "A2", "status": "Draft"})
    await ctx.db._session().commit()

    rows = await ctx.db.aggregate(
        "TestItem",
        group_by="date(created_at)",
        aggregations={"n": "count"},
    )
    assert len(rows) == 1
    assert rows[0]["n"] == 2
    assert "date(created_at)" in rows[0]


LINK_TARGET_DOCTYPE = {
    "name": "LinkLabelTarget",
    "label": "Link Label Target",
    "module": "core",
    "title_field": "title",
    "image_field": "photo",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {"fieldname": "color", "label": "Color", "fieldtype": "Color"},
        {"fieldname": "icon", "label": "Icon", "fieldtype": "Icon"},
        {"fieldname": "photo", "label": "Photo", "fieldtype": "Attach"},
    ],
}

LINK_SOURCE_DOCTYPE = {
    "name": "LinkLabelSource",
    "label": "Link Label Source",
    "module": "core",
    "fields": [
        {
            "fieldname": "target",
            "label": "Target",
            "fieldtype": "Link",
            "options": "LinkLabelTarget",
        },
    ],
}


@pytest.fixture
async def link_label_doctypes(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**LINK_TARGET_DOCTYPE, "__is_new": True})
    await save_doctype(doctype_data={**LINK_SOURCE_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_get_list_injects_link_field_labels_and_extras(ctx, link_label_doctypes):
    """list_documents resolves Link fields to __label/__color/__icon/__image."""
    target = await ctx.new_doc(
        "LinkLabelTarget",
        {"title": "Widget", "color": "#ff0000", "icon": "star", "photo": "/files/widget.png"},
    )
    await ctx.new_doc("LinkLabelSource", {"target": target["name"]})
    await ctx.db._session().commit()

    rows = await ctx.get_list("LinkLabelSource", fields=["target"])
    assert len(rows) == 1
    row = rows[0]
    assert row["target__label"] == "Widget"
    assert row["target__color"] == "#ff0000"
    assert row["target__icon"] == "star"
    assert row["target__image"] == "/files/widget.png"


@pytest.mark.asyncio
async def test_get_list_link_label_falls_back_to_raw_id_for_dangling_link(ctx, link_label_doctypes):
    """A Link value pointing at a non-existent target still gets a __label (itself)."""
    await ctx.new_doc("LinkLabelSource", {"target": "does-not-exist"})
    await ctx.db._session().commit()

    rows = await ctx.get_list("LinkLabelSource", fields=["target"])
    assert rows[0]["target__label"] == "does-not-exist"
    assert rows[0]["target__image"] == ""


@pytest.mark.asyncio
async def test_rename_document_cascades_to_link_fields(ctx, link_label_doctypes):
    """rename_doc updates the main row and every Link field pointing at it."""
    target = await ctx.new_doc("LinkLabelTarget", {"title": "Widget"})
    source = await ctx.new_doc("LinkLabelSource", {"target": target["name"]})
    await ctx.db._session().commit()

    renamed = await ctx.rename_doc("LinkLabelTarget", target["name"], "widget-new-id")
    assert renamed["name"] == "widget-new-id"

    refetched_source = await ctx.get_doc("LinkLabelSource", source["name"])
    assert refetched_source["target"] == "widget-new-id"

    with pytest.raises(Exception):  # noqa: B017 - HTTPException 404, old id is gone
        await ctx.get_doc("LinkLabelTarget", target["name"])


@pytest.mark.asyncio
async def test_rename_document_rejects_existing_new_id(ctx, link_label_doctypes):
    """rename_doc 409s rather than silently merging into an existing document."""
    from fastapi import HTTPException

    await ctx.new_doc("LinkLabelTarget", {"title": "A", "name": "existing-id"})
    doc_to_rename = await ctx.new_doc("LinkLabelTarget", {"title": "B"})
    await ctx.db._session().commit()

    with pytest.raises(HTTPException) as exc_info:
        await ctx.rename_doc("LinkLabelTarget", doc_to_rename["name"], "existing-id")
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_rename_document_cascades_to_multilink_refs(ctx, link_label_doctypes):
    """rename_doc updates grunt_core_multi_link rows on both the parent and link side."""
    from grunt.metadata.compiler import MULTI_LINK_TABLE

    target = await ctx.new_doc("LinkLabelTarget", {"title": "Widget"})
    session = ctx.db._session()
    await session.execute(
        MULTI_LINK_TABLE.insert().values(
            parent_doctype="LinkLabelSource",
            parent_name="some-source",
            parent_field="targets",
            idx=0,
            link_doctype="LinkLabelTarget",
            link_name=target["name"],
        )
    )
    await session.commit()

    await ctx.rename_doc("LinkLabelTarget", target["name"], "widget-new-id")

    row = (
        await session.execute(
            MULTI_LINK_TABLE.select().where(MULTI_LINK_TABLE.c.parent_name == "some-source")
        )
    ).first()
    assert row.link_name == "widget-new-id"


@pytest.mark.asyncio
async def test_bulk_delete_documents(ctx, setup_doctype):
    """bulk_delete_docs removes multiple docs and reports missing IDs."""
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    a = await ctx.new_doc("TestItem", {"title": "Bulk A"})
    b = await ctx.new_doc("TestItem", {"title": "Bulk B"})
    await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx.get_engine(), SYSTEM_USER):
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

    async with ctx.context(ctx.db._session(), ctx.get_engine(), SYSTEM_USER):
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
    """Document.link_search should return compact rows and honor title/search fields."""
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.document.base import Document

    await ctx.new_doc("TestItem", {"title": "Alpha Item", "status": "Draft"})
    await ctx.new_doc("TestItem", {"title": "Beta Item", "status": "Active"})
    await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx.get_engine(), SYSTEM_USER):
        items = await Document.link_search(
            "TestItem",
            search="Alpha",
            filters={"status": "Draft"},
            per_page=10,
        )

    assert len(items) == 1
    assert items[0]["title"] == "Alpha Item"
    # The document id is never surfaced as subtitle/fields in the dropdown.
    assert items[0]["subtitle"] is None
    assert items[0]["fields"] == []
    assert items[0]["name"] not in (items[0]["subtitle"], items[0]["title"])


@pytest.mark.asyncio
async def test_link_search_returns_all_search_fields(ctx):
    """`fields` carries every configured search_field (label + value) minus the
    one already shown as the title, so the dropdown can display the data the
    user searched by."""
    from grunt.api.v1.meta import save_doctype
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.document.base import Document

    await save_doctype(
        doctype_data={
            "name": "Correspondentish",
            "label": "Correspondentish",
            "module": "core",
            "title_field": "name_full",
            "fields": [
                {"fieldname": "name_full", "label": "Повна назва", "fieldtype": "Data"},
                {"fieldname": "short_name", "label": "Скорочена назва", "fieldtype": "Data"},
                {"fieldname": "edrpou", "label": "ЄДРПОУ", "fieldtype": "Data"},
            ],
            "search_fields": ["name_full", "short_name", "edrpou"],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    await ctx.new_doc(
        "Correspondentish",
        {
            "name_full": "Адміністрація Держспецзв'язку України",
            "short_name": "АДМІНІСТРАЦІЯ ДЕРЖСПЕЦЗВ'ЯЗКУ",
            "edrpou": "34620942",
        },
    )
    await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx.get_engine(), SYSTEM_USER):
        items = await Document.link_search("Correspondentish", search="34620942")

    assert len(items) == 1
    item = items[0]
    assert item["title"] == "Адміністрація Держспецзв'язку України"
    # name_full is the title → dropped; the other two search fields remain, in order.
    assert item["fields"] == [
        {
            "fieldname": "short_name",
            "label": "Скорочена назва",
            "value": "АДМІНІСТРАЦІЯ ДЕРЖСПЕЦЗВ'ЯЗКУ",
        },
        {"fieldname": "edrpou", "label": "ЄДРПОУ", "value": "34620942"},
    ]


@pytest.mark.asyncio
async def test_copy_doc(ctx, setup_doctype):
    """copy_doc clones every field but id/name/created_at, applies overrides,
    and inserts a fresh document."""
    original = await ctx.new_doc("TestItem", {"title": "Original", "status": "Active", "count": 7})
    await ctx.db._session().commit()

    copy = await ctx.copy_doc("TestItem", original["name"], overrides={"status": "Draft"})
    await ctx.db._session().commit()

    assert copy["name"] != original["name"]
    assert copy["title"] == "Original"  # copied
    assert copy["count"] == 7  # copied
    assert copy["status"] == "Draft"  # overridden
    # original untouched
    again = await ctx.get_doc("TestItem", original["name"])
    assert again["status"] == "Active"


@pytest.mark.asyncio
async def test_create_rejects_value_over_max_length(ctx):
    """A Data value longer than max_length → 422, even on SQLite where the
    underlying VARCHAR column itself would silently accept it."""
    from fastapi import HTTPException

    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            "name": "MaxLenItem",
            "label": "Max Len Item",
            "module": "core",
            "fields": [
                {"fieldname": "code", "label": "Code", "fieldtype": "Data", "max_length": 100},
            ],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    with pytest.raises(HTTPException) as exc:
        await ctx.new_doc("MaxLenItem", {"code": "x" * 150})
    assert exc.value.status_code == 422
    assert "100" in exc.value.detail[0]

    ok = await ctx.new_doc("MaxLenItem", {"code": "x" * 100})
    await ctx.db._session().commit()
    assert ok["code"] == "x" * 100


@pytest.mark.asyncio
async def test_create_rejects_value_outside_min_max(ctx):
    """An Int value outside [min_value, max_value] → 422."""
    from fastapi import HTTPException

    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            "name": "RangeItem",
            "label": "Range Item",
            "module": "core",
            "fields": [
                {
                    "fieldname": "score",
                    "label": "Score",
                    "fieldtype": "Int",
                    "min_value": 0,
                    "max_value": 100,
                },
            ],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    with pytest.raises(HTTPException) as exc:
        await ctx.new_doc("RangeItem", {"score": 150})
    assert exc.value.status_code == 422
    assert "100" in exc.value.detail[0]

    with pytest.raises(HTTPException) as exc:
        await ctx.new_doc("RangeItem", {"score": -1})
    assert exc.value.status_code == 422

    ok = await ctx.new_doc("RangeItem", {"score": 42})
    await ctx.db._session().commit()
    assert ok["score"] == 42


@pytest.mark.asyncio
async def test_create_rejects_value_not_matching_regex(ctx):
    """A Data value that doesn't match the field's regex → 422."""
    from fastapi import HTTPException

    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            "name": "RegexItem",
            "label": "Regex Item",
            "module": "core",
            "fields": [
                {
                    "fieldname": "code",
                    "label": "Code",
                    "fieldtype": "Data",
                    "regex": r"^[A-Z]{3}-\d{4}$",
                },
            ],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    with pytest.raises(HTTPException) as exc:
        await ctx.new_doc("RegexItem", {"code": "not-a-match"})
    assert exc.value.status_code == 422

    ok = await ctx.new_doc("RegexItem", {"code": "ABC-1234"})
    await ctx.db._session().commit()
    assert ok["code"] == "ABC-1234"


@pytest.mark.asyncio
async def test_lifecycle_hooks_see_submitted_multilink(ctx):
    """validate()/after_save() see the submitted MultiLink list on create and
    on update — not the stale stored one (or nothing at all on create)."""
    from grunt.api.v1.meta import save_doctype
    from grunt.document.base import Document
    from grunt.document.registry import document_registry

    await save_doctype(
        doctype_data={
            "name": "HookWatchItem",
            "label": "Hook Watch Item",
            "module": "core",
            "fields": [
                {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
                {
                    "fieldname": "watchers",
                    "label": "Watchers",
                    "fieldtype": "MultiLink",
                    "options": "User",
                },
            ],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    seen: list[tuple[str, object]] = []

    class HookWatchItem(Document):
        async def validate(self) -> None:
            seen.append(("validate", self.data.get("watchers")))

        async def after_save(self) -> None:
            seen.append(("after_save", self.data.get("watchers")))

    document_registry.register("HookWatchItem", HookWatchItem)
    try:
        created = await ctx.new_doc(
            "HookWatchItem", {"title": "x", "watchers": ["system@grunt.local"]}
        )
        assert seen == [
            ("validate", ["system@grunt.local"]),
            ("after_save", ["system@grunt.local"]),
        ]
        seen.clear()
        await ctx.save_doc("HookWatchItem", created["name"], {"watchers": []})
        assert seen == [("validate", []), ("after_save", [])]
    finally:
        document_registry._controllers.pop("HookWatchItem", None)
