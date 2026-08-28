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

    # No id at all — Frappe-style `get_doc('System Settings')`.
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
