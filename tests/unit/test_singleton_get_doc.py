"""Singleton DocTypes are fetchable without (or with a mismatched) id."""

import pytest


async def _clear_system_settings(ctx) -> None:
    """The shared conftest seeds a permissive SystemSettings row; these tests
    exercise the empty-singleton / first-create paths, so start from scratch."""
    from grunt.metadata.compiler import compile_doctype_to_table
    from grunt.metadata.registry import doctype_registry

    table = compile_doctype_to_table(await doctype_registry.get("SystemSettings"))
    await ctx.db._session().execute(table.delete())
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_get_doc_singleton_without_id(ctx):
    await _clear_system_settings(ctx)
    await ctx.new_doc("SystemSettings", {"app_name": "Acme"})

    # No id at all — `get_doc('System Settings')`.
    doc = await ctx.get_doc("SystemSettings")
    assert doc["app_name"] == "Acme"

    # A mismatched id is ignored for singletons (the row is autonamed).
    assert doc["name"] != "SystemSettings"
    same = await ctx.get_doc("SystemSettings", "SystemSettings")
    assert same["name"] == doc["name"]

    found = await ctx.find_doc("SystemSettings")
    assert found is not None and found["name"] == doc["name"]


@pytest.mark.asyncio
async def test_get_doc_singleton_missing_row_404(ctx):
    from fastapi import HTTPException

    await _clear_system_settings(ctx)

    with pytest.raises(HTTPException) as exc:
        await ctx.get_doc("SystemSettings")
    assert exc.value.status_code == 404
    assert await ctx.find_doc("SystemSettings") is None


@pytest.mark.asyncio
async def test_save_doc_creates_missing_singleton_row(ctx):
    """The form has no separate "new" state for a singleton — the first save
    routes as an update (id == DocType name). ``update_document`` must upsert:
    create the sole row on first save instead of raising 404."""
    await _clear_system_settings(ctx)

    saved = await ctx.save_doc("SystemSettings", "SystemSettings", {"app_name": "Acme"})
    assert saved["app_name"] == "Acme"
    # First save names the row after the DocType.
    assert saved["name"] == "SystemSettings"

    # A subsequent save updates that same row rather than creating a second one.
    again = await ctx.save_doc("SystemSettings", "SystemSettings", {"app_name": "Beta"})
    assert again["name"] == "SystemSettings"
    assert (await ctx.get_doc("SystemSettings"))["app_name"] == "Beta"
