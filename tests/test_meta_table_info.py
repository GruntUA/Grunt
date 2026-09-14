"""Tests for grunt.api.v1.meta.table_info — physical storage info for a DocType."""

from __future__ import annotations

import pytest

TABLE_INFO_DOCTYPE = {
    "name": "StorageProbe",
    "label": "Storage Probe",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {"fieldname": "note", "label": "Note", "fieldtype": "LongText"},
    ],
    "search_fields": ["title"],
}


@pytest.fixture
async def probe_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**TABLE_INFO_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_table_info_reports_physical_table(ctx, probe_doctype):
    from grunt.api.v1.meta import table_info

    for i in range(3):
        await ctx.new_doc("StorageProbe", {"title": f"row {i}"})
    await ctx.db._session().commit()

    info = await table_info(name="StorageProbe")

    assert info["doctype"] == "StorageProbe"
    assert info["table_name"] == "grunt_core_storage_probe"
    assert info["dialect"] == "sqlite"
    assert info["exists"] is True
    assert info["row_count"] == 3

    # dbstat is usually compiled into pysqlite; when it is, sizes are real ints.
    if info["size_supported"]:
        assert info["table_bytes"] >= 0
        assert info["index_bytes"] >= 0
        assert info["total_bytes"] == info["table_bytes"] + info["index_bytes"]
        assert info["reclaim_scope"] == "database"
    else:
        assert info["total_bytes"] is None


@pytest.mark.asyncio
async def test_table_info_rejects_virtual_doctype(ctx):
    from grunt.api.messages import ApplicationError
    from grunt.api.v1.meta import save_doctype, table_info

    await save_doctype(
        doctype_data={
            "name": "VirtualProbe",
            "label": "Virtual Probe",
            "module": "core",
            "is_virtual": True,
            "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()

    with pytest.raises(ApplicationError):
        await table_info(name="VirtualProbe")


@pytest.mark.asyncio
async def test_compact_table_reports_freed_space(ctx, probe_doctype):
    from grunt.api.v1.meta import compact_table, table_info

    # Grow the file, then delete everything so VACUUM has slack to reclaim.
    blob = "x" * 6000
    for i in range(120):
        await ctx.new_doc("StorageProbe", {"title": f"row {i}", "note": blob})
    await ctx.db._session().commit()

    for row in await ctx.get_list("StorageProbe", fields=["name"], limit=1000):
        await ctx.delete_doc("StorageProbe", row["name"])
    await ctx.db._session().commit()

    before = await table_info(name="StorageProbe")
    result = await compact_table(name="StorageProbe")

    assert result["command"] == "VACUUM"
    assert result["scope"] == "database"
    assert result["before_bytes"] >= result["after_bytes"] >= 0
    assert result["freed_bytes"] == result["before_bytes"] - result["after_bytes"]
    assert result["freed_bytes"] > 0

    after = await table_info(name="StorageProbe")
    if before["size_supported"] and after["size_supported"]:
        assert after["total_bytes"] <= before["total_bytes"]


@pytest.mark.asyncio
async def test_compact_table_requires_system_manager(db_session, engine):
    from fastapi import HTTPException

    from grunt.api.v1.meta import compact_table
    from grunt.app import grunt as grunt_app
    from tests.support import make_user

    async with grunt_app.context(db_session, engine, make_user("nobody@grunt.example.com")):
        with pytest.raises(HTTPException):
            await compact_table(name="DocType")


@pytest.mark.asyncio
async def test_table_info_requires_system_manager(db_session, engine):
    """A plain user (no roles) gets a 403 before the body runs."""
    from fastapi import HTTPException

    from grunt.api.v1.meta import table_info
    from grunt.app import grunt as grunt_app
    from tests.support import make_user

    async with grunt_app.context(db_session, engine, make_user("nobody@grunt.example.com")):
        with pytest.raises(HTTPException):
            await table_info(name="DocType")
