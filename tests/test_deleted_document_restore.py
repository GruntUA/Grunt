"""Soft-delete trash bin: deleting a document snapshots it into
``DeletedDocument``; :func:`restore` brings it back with the same id and
child rows, and refuses a second restore.
"""

import pytest

_TRASH_DOCTYPE = {
    "name": "TrashItem",
    "label": "Trash Item",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data", "required": True},
        {"fieldname": "qty", "label": "Qty", "fieldtype": "Int"},
        {"fieldname": "due", "label": "Due", "fieldtype": "Date"},
        {
            "fieldname": "rows",
            "label": "Rows",
            "fieldtype": "Table",
            "options": "TrashItemRow",
        },
    ],
    "search_fields": ["title"],
}

_TRASH_CHILD_DOCTYPE = {
    "name": "TrashItemRow",
    "label": "Trash Item Row",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "label", "label": "Label", "fieldtype": "Data"},
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Int"},
        {"fieldname": "on_date", "label": "On Date", "fieldtype": "Date"},
    ],
}


async def _child_rows(ctx, parent: str) -> list[dict]:
    return await ctx.db.get_all("TrashItemRow", filters={"parent_name": parent}, fields=["name"])


@pytest.fixture
async def setup_trash_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_TRASH_CHILD_DOCTYPE, "__is_new": True})
    await save_doctype(doctype_data={**_TRASH_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_delete_creates_snapshot_and_restore_round_trips(ctx, setup_trash_doctype):
    doc = await ctx.new_doc(
        "TrashItem",
        {
            "title": "Widget",
            "qty": 7,
            "rows": [{"label": "a", "amount": 1}, {"label": "b", "amount": 2}],
        },
    )
    name = doc["name"]
    await ctx.db._session().commit()

    await ctx.delete_doc("TrashItem", name)
    await ctx.db._session().commit()

    # gone from its own table …
    assert not await ctx.db.exists("TrashItem", name)

    # … but snapshotted
    snaps = await ctx.get_list(
        "DeletedDocument",
        filters={"deleted_doctype": "TrashItem", "deleted_name": name},
    )
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap["restored"] in (0, False)
    assert snap["title"] == "Widget"
    assert snap["data"]["qty"] == 7
    assert len(snap["data"]["rows"]) == 2

    from grunt.activity.doctypes.DeletedDocument.deleted_document import restore
    from grunt.api.messages import ApplicationError

    restored = await restore(snap["name"])
    await ctx.db._session().commit()

    assert restored["name"] == name  # hash autoname → original id preserved
    assert restored["qty"] == 7
    assert await ctx.db.exists("TrashItem", name)

    fresh = await ctx.get_doc("TrashItem", name)
    assert {r["label"] for r in fresh["rows"]} == {"a", "b"}

    # snapshot marked restored, second restore refused
    snap_after = await ctx.get_doc("DeletedDocument", snap["name"])
    assert snap_after["restored"] in (1, True)
    assert snap_after["restored_to"] == name

    with pytest.raises(ApplicationError):
        await restore(snap["name"])


@pytest.mark.asyncio
async def test_delete_removes_child_rows_and_snapshots_dates(ctx, setup_trash_doctype):
    doc = await ctx.new_doc(
        "TrashItem",
        {
            "title": "Dated",
            "due": "2026-05-04",
            "rows": [{"label": "a", "amount": 1, "on_date": "2026-05-05"}],
        },
    )
    name = doc["name"]
    await ctx.db._session().commit()
    assert len(await _child_rows(ctx, name)) == 1

    await ctx.delete_doc("TrashItem", name)
    await ctx.db._session().commit()
    assert await _child_rows(ctx, name) == []

    snaps = await ctx.get_list(
        "DeletedDocument", filters={"deleted_doctype": "TrashItem", "deleted_name": name}
    )
    assert len(snaps) == 1
    assert snaps[0]["data"]["due"] == "2026-05-04"
    assert snaps[0]["data"]["rows"][0]["on_date"] == "2026-05-05"

    from grunt.activity.doctypes.DeletedDocument.deleted_document import restore

    await restore(snaps[0]["name"])
    await ctx.db._session().commit()
    fresh = await ctx.get_doc("TrashItem", name)
    assert str(fresh["due"])[:10] == "2026-05-04"
    assert [str(r["on_date"])[:10] for r in fresh["rows"]] == ["2026-05-05"]


@pytest.mark.asyncio
async def test_bulk_delete_removes_child_rows(ctx, setup_trash_doctype):
    doc = await ctx.new_doc("TrashItem", {"title": "Bulk", "rows": [{"label": "a"}]})
    other = await ctx.new_doc("TrashItem", {"title": "Stays", "rows": [{"label": "b"}]})
    await ctx.db._session().commit()

    deleted, errors = await ctx.bulk_delete_docs("TrashItem", [doc["name"]])
    await ctx.db._session().commit()

    assert (deleted, errors) == (1, [])
    assert await _child_rows(ctx, doc["name"]) == []
    assert len(await _child_rows(ctx, other["name"])) == 1


@pytest.mark.asyncio
async def test_restore_with_name_taken_requires_allow_rename(ctx, setup_trash_doctype):
    doc = await ctx.new_doc("TrashItem", {"title": "Dup", "qty": 1})
    name = doc["name"]
    await ctx.db._session().commit()

    await ctx.delete_doc("TrashItem", name)
    await ctx.db._session().commit()

    # recreate a live document with the same id
    await ctx.new_doc("TrashItem", {"name": name, "title": "Dup again", "qty": 2})
    await ctx.db._session().commit()

    snap = (
        await ctx.get_list(
            "DeletedDocument",
            filters={"deleted_doctype": "TrashItem", "deleted_name": name},
        )
    )[0]

    from grunt.activity.doctypes.DeletedDocument.deleted_document import restore
    from grunt.api.messages import ApplicationError

    with pytest.raises(ApplicationError):
        await restore(snap["name"])

    renamed = await restore(snap["name"], allow_rename=True)
    await ctx.db._session().commit()
    assert renamed["name"] != name
    assert renamed["title"] == "Dup"


@pytest.mark.asyncio
async def test_track_deletions_false_skips_snapshot(ctx, setup_trash_doctype):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_TRASH_DOCTYPE, "track_deletions": False})
    await ctx.db._session().commit()

    doc = await ctx.new_doc("TrashItem", {"title": "Ephemeral", "qty": 3})
    name = doc["name"]
    await ctx.db._session().commit()

    await ctx.delete_doc("TrashItem", name)
    await ctx.db._session().commit()

    snaps = await ctx.get_list(
        "DeletedDocument", filters={"deleted_doctype": "TrashItem", "deleted_name": name}
    )
    assert snaps == []
