"""Table widget: ``row_limit`` caps the rows (the biggest values first)."""

import pytest

from grunt.reports.widget_compute import _widget_table

pytestmark = pytest.mark.asyncio

DT = {
    "name": "WtItem",
    "label": "Wt Item",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "points", "label": "Points", "fieldtype": "Float"},
    ],
}


@pytest.fixture
async def items(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**DT, "__is_new": True})
    for i in range(5):
        await ctx.new_doc("WtItem", {"title": f"t{i}", "points": i})
    await ctx.db._session().commit()


async def _rows(ctx, **widget):
    dt = await ctx.get_meta("WtItem")
    widget = {"group_by": "title", "aggregation": "sum", "field": "points", **widget}
    data = await _widget_table(widget, dt, "WtItem", None, None, 30, {})
    return [r["label"] for r in data["rows"]]


async def test_row_limit(ctx, items):
    assert await _rows(ctx) == ["t4", "t3", "t2", "t1", "t0"]
    assert await _rows(ctx, row_limit=2) == ["t4", "t3"]
    assert len(await _rows(ctx, row_limit=0)) == 5
