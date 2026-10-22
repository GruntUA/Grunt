"""HTMLView field: server-built markup, sanitized on every write path."""

import pytest

REPORT = {
    "name": "HtmlReport",
    "label": "HTML Report",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "summary", "label": "Summary", "fieldtype": "HTMLView", "read_only": True},
    ],
    "permissions": [{"role": "System Manager", "read": True, "write": True, "create": True}],
}
DIRTY = '<table><tr><td onmouseover="steal()">1</td></tr></table><script>alert(1)</script>'
CLEAN = "<table><tbody><tr><td>1</td></tr></tbody></table>"


async def _report_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**REPORT, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_save_doc_sanitizes(ctx):
    await _report_doctype(ctx)
    doc = await ctx.new_doc("HtmlReport", {"title": "Q3", "summary": DIRTY})

    assert (await ctx.get_doc("HtmlReport", doc["name"]))["summary"] == CLEAN


@pytest.mark.asyncio
async def test_set_value_sanitizes(ctx):
    await _report_doctype(ctx)
    doc = await ctx.new_doc("HtmlReport", {"title": "Q3"})
    await ctx.db.set_value("HtmlReport", doc["name"], "summary", DIRTY)

    assert (await ctx.get_doc("HtmlReport", doc["name"]))["summary"] == CLEAN
