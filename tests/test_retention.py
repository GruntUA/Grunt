"""DocType.retention_days: old documents are deleted — business documents
through the normal delete (trash snapshot), logs in bulk."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

NOW = datetime(2026, 9, 23, tzinfo=UTC)

BOX = {
    "name": "RetainBox",
    "label": "Retain Box",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "closed_on", "label": "Closed on", "fieldtype": "Date"},
    ],
    "permissions": [{"role": "System Manager", "read": True, "delete": True, "create": True}],
}


async def _box(ctx, **extra):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, **extra, "__is_new": True})
    await ctx.db._session().commit()
    return await ctx.get_meta("RetainBox")


async def _doc(ctx, title: str, created: datetime, **data) -> str:
    name = (await ctx.new_doc("RetainBox", {"title": title, **data}))["name"]
    await ctx.db.set_value("RetainBox", name, "created_at", created)
    return name


@pytest.mark.asyncio
async def test_without_retention_nothing_is_deleted(ctx):
    from grunt.tasks.retention import purge_doctype

    meta = await _box(ctx)
    await _doc(ctx, "ancient", NOW - timedelta(days=5000))
    assert await purge_doctype(meta.doc, NOW, log_default=30) == 0


@pytest.mark.asyncio
async def test_old_documents_deleted_into_trash(ctx):
    from grunt.tasks.retention import purge_doctype

    meta = await _box(ctx, retention_days=365)
    old = await _doc(ctx, "old", NOW - timedelta(days=400))
    fresh = await _doc(ctx, "fresh", NOW - timedelta(days=10))
    await ctx.db._session().commit()

    assert await purge_doctype(meta.doc, NOW, log_default=30) == 1
    await ctx.db._session().commit()

    assert not await ctx.db.exists("RetainBox", old)
    assert await ctx.db.exists("RetainBox", fresh)
    # Normal delete pipeline → restorable snapshot in the trash.
    assert await ctx.db.exists(
        "DeletedDocument", {"deleted_doctype": "RetainBox", "deleted_name": old}
    )


@pytest.mark.asyncio
async def test_retention_counts_from_chosen_date_field(ctx):
    from grunt.tasks.retention import purge_doctype

    meta = await _box(ctx, retention_days=30, retention_date_field="closed_on")
    # Created long ago but closed recently → kept; closed long ago → deleted.
    kept = await _doc(ctx, "k", NOW - timedelta(days=900), closed_on="2026-09-10")
    gone = await _doc(ctx, "g", NOW, closed_on="2026-01-01")
    open_ = await _doc(ctx, "o", NOW - timedelta(days=900))  # never closed
    await ctx.db._session().commit()

    assert await purge_doctype(meta.doc, NOW, log_default=30) == 1
    await ctx.db._session().commit()
    assert await ctx.db.exists("RetainBox", kept)
    assert await ctx.db.exists("RetainBox", open_)
    assert not await ctx.db.exists("RetainBox", gone)


@pytest.mark.asyncio
async def test_log_doctypes_use_site_default(ctx):
    from grunt.tasks.retention import purge_doctype

    meta = await ctx.get_meta("ErrorLog")
    assert meta.doc.is_log and not meta.doc.retention_days
    await ctx.db.insert_one(
        "ErrorLog",
        {
            "name": "old-err",
            "owner": "system",
            "created_at": NOW - timedelta(days=40),
            "modified_at": NOW - timedelta(days=40),
            "modified_by": "system",
        },
    )
    await ctx.db._session().commit()

    assert await purge_doctype(meta.doc, NOW, log_default=30) >= 1
    assert not await ctx.db.exists("ErrorLog", "old-err")
