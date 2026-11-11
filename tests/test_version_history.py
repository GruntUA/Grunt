"""Version history: fields left out of it (``no_history``) and its size per
document (``DocType.max_versions``)."""

import pytest

from grunt.document.versioning import version_service

NOTE = {
    "name": "VhNote",
    "label": "VH Note",
    "module": "core",
    "max_versions": 3,
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "sync_status", "label": "Sync", "fieldtype": "Data", "no_history": True},
    ],
    "permissions": [{"role": "System Manager", "actions": ["read", "write", "create", "delete"]}],
}


@pytest.fixture
async def note(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**NOTE, "__is_new": True})
    doc = await ctx.new_doc("VhNote", {"title": "v0"})
    await ctx.db._session().commit()
    return doc["name"]


async def _versions(ctx, name) -> list[dict]:
    return await version_service.get_versions(ctx.db._session(), "VhNote", name)


async def test_no_history_field_leaves_no_version_or_activity(ctx, note):
    await ctx.save_doc("VhNote", note, {"sync_status": "running"})
    assert await _versions(ctx, note) == []
    activity = await ctx.db.get_all(
        "ActivityLog",
        filters={"ref_doctype": "VhNote", "doc_id": note, "action": "Update"},
        limit=5,
    )
    assert activity == []

    # Together with a tracked field: a version, without the quiet field.
    await ctx.save_doc("VhNote", note, {"title": "v1", "sync_status": "done"})
    [version] = await _versions(ctx, note)
    assert [c["field"] for c in version["changes"]] == ["title"]


async def test_only_the_newest_versions_are_kept(ctx, note):
    for i in range(1, 6):
        await ctx.save_doc("VhNote", note, {"title": f"v{i}"})
    versions = await _versions(ctx, note)
    assert [v["version"] for v in versions] == [5, 4, 3]
    assert versions[0]["changes"][0]["new"] == "v5"


async def test_zero_keeps_every_version(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**NOTE, "name": "VhAll", "max_versions": 0, "__is_new": True})
    name = (await ctx.new_doc("VhAll", {"title": "v0"}))["name"]
    for i in range(1, 5):
        await ctx.save_doc("VhAll", name, {"title": f"v{i}"})
    versions = await version_service.get_versions(ctx.db._session(), "VhAll", name)
    assert len(versions) == 4


async def test_the_limit_counts_existing_versions_not_numbers(ctx, note):
    """A gap in the numbers (a version deleted by hand) keeps a record that fits."""
    from sqlalchemy import delete

    for i in (1, 2, 3):
        await ctx.save_doc("VhNote", note, {"title": f"v{i}"})
    table = (await ctx.get_meta("DocVersion")).table
    await ctx.db._session().execute(
        delete(table).where(table.c.doc_id == note).where(table.c.version == 2)
    )
    await ctx.save_doc("VhNote", note, {"title": "v4"})  # keeps 1, 3, 4 - three of them
    assert [v["version"] for v in await _versions(ctx, note)] == [4, 3, 1]
