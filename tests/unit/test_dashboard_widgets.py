"""Tests for dashboard widget computation (api/v1/dashboard.py).

No prior coverage existed for this module before _compute_widget_data's
10-branch if/elif chain was split into a widget_type -> handler dispatch
table, and get_page_data/get_dashboard_data were unified into a shared
_get_widget_data(). These tests exercise a representative widget type per
handler family plus both entry points end-to-end.
"""

from __future__ import annotations

import pytest

WIDGET_SOURCE_DOCTYPE = {
    "name": "WidgetSourceItem",
    "label": "Widget Source Item",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "Draft\nActive\nArchived",
        },
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Int"},
    ],
}


@pytest.fixture
async def widget_source(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**WIDGET_SOURCE_DOCTYPE, "__is_new": True})
    await ctx.new_doc("WidgetSourceItem", {"title": "A", "status": "Active", "amount": 10})
    await ctx.new_doc("WidgetSourceItem", {"title": "B", "status": "Active", "amount": 20})
    await ctx.new_doc("WidgetSourceItem", {"title": "C", "status": "Draft", "amount": 5})
    await ctx.db._session().commit()


def _widget(widget_type: str, **kwargs) -> dict:
    return {
        "name": f"w-{widget_type}",
        "widget_type": widget_type,
        "doctype": "WidgetSourceItem",
        "period": "last_month",
        **kwargs,
    }


@pytest.mark.asyncio
async def test_metric_widget_counts_all_rows(ctx, widget_source):
    from grunt.api.v1.dashboard import _compute_widget_data

    result = await _compute_widget_data(_widget("metric", aggregation="count"))
    assert result["value"] == 3


@pytest.mark.asyncio
async def test_metric_widget_sums_a_field(ctx, widget_source):
    from grunt.api.v1.dashboard import _compute_widget_data

    result = await _compute_widget_data(_widget("metric", aggregation="sum", field="amount"))
    assert result["value"] == 35


@pytest.mark.asyncio
async def test_donut_widget_groups_by_field(ctx, widget_source):
    from grunt.api.v1.dashboard import _compute_widget_data

    result = await _compute_widget_data(_widget("donut", group_by="status"))
    assert dict(zip(result["labels"], result["values"], strict=True)) == {
        "Active": 2,
        "Draft": 1,
    }


@pytest.mark.asyncio
async def test_list_widget_returns_items_and_title_field(ctx, widget_source):
    from grunt.api.v1.dashboard import _compute_widget_data

    result = await _compute_widget_data(_widget("list"))
    assert len(result["items"]) == 3
    assert "title_field" in result


@pytest.mark.asyncio
async def test_shortcut_widget_counts_documents(ctx, widget_source):
    from grunt.api.v1.dashboard import _compute_widget_data

    result = await _compute_widget_data(_widget("shortcut"))
    assert result["count"] == 3


@pytest.mark.asyncio
async def test_table_widget_groups_and_sums(ctx, widget_source):
    from grunt.api.v1.dashboard import _compute_widget_data

    result = await _compute_widget_data(
        _widget("table", group_by="status", aggregation="sum", field="amount")
    )
    rows = {r["label"]: r["value"] for r in result["rows"]}
    assert rows == {"Active": 30.0, "Draft": 5.0}


@pytest.mark.asyncio
async def test_unknown_widget_type_returns_none(ctx, widget_source):
    from grunt.api.v1.dashboard import _compute_widget_data

    result = await _compute_widget_data(_widget("not_a_real_widget_type"))
    assert result is None


@pytest.mark.asyncio
async def test_chart_widget_sourced_from_report(ctx, widget_source):
    """A chart_bar widget with `report` set draws its series from that report."""
    from grunt.api.v1.dashboard import _compute_widget_data

    await ctx.new_doc(
        "Report",
        {
            "report_name": "Widget Src By Status",
            "report_type": "List",
            "doctype": "WidgetSourceItem",
            "columns": [
                {"fieldname": "status", "label": "Status"},
                {
                    "fieldname": "amount",
                    "label": "Amount",
                    "aggregation": "sum",
                    "fieldtype": "Int",
                },
            ],
            "chart_config": {"type": "bar", "label_field": "status", "value_fields": ["amount"]},
        },
    )
    await ctx.db._session().commit()

    result = await _compute_widget_data(
        _widget("chart_bar", doctype="", report="Widget Src By Status")
    )
    series = dict(zip(result["labels"], result["values"], strict=True))
    assert series == {"Active": 30.0, "Draft": 5.0}


@pytest.mark.asyncio
async def test_report_sourced_widget_missing_report_is_empty(ctx, widget_source):
    from grunt.api.v1.dashboard import _compute_widget_data

    result = await _compute_widget_data(_widget("donut", doctype="", report="No Such Report"))
    assert result == {"labels": [], "values": []}


@pytest.mark.asyncio
async def test_get_page_data_computes_all_widgets_by_name(ctx, widget_source):
    from grunt.api.v1.dashboard import get_page_data

    await ctx.new_doc(
        "Page",
        {
            "name": "Test Page",
            "label": "Test Page",
            "is_published": True,
            "widgets": [
                {"widget_type": "metric", "doctype": "WidgetSourceItem"},
                {"widget_type": "shortcut", "doctype": "WidgetSourceItem"},
            ],
        },
    )
    await ctx.db._session().commit()

    result = await get_page_data("Test Page")
    # Child-row names are framework-assigned — key on computed content instead.
    values = sorted(result.values(), key=str)
    assert {"value": 3, "trend": None} in values
    assert {"count": 3} in values


@pytest.mark.asyncio
async def test_get_dashboard_data_matches_get_page_data_shape(ctx, widget_source):
    """Both entry points go through the same _get_widget_data — same result shape."""
    from grunt.api.v1.dashboard import get_dashboard_data

    await ctx.new_doc(
        "Dashboard",
        {
            "name": "Test Dashboard",
            "label": "Test Dashboard",
            "is_published": True,
            "widgets": [
                {"widget_type": "shortcut", "doctype": "WidgetSourceItem"},
            ],
        },
    )
    await ctx.db._session().commit()

    result = await get_dashboard_data("Test Dashboard")
    assert list(result.values()) == [{"count": 3}]


@pytest.mark.asyncio
async def test_get_page_data_not_found_raises(ctx, widget_source):
    from grunt.api.messages import ApplicationError
    from grunt.api.v1.dashboard import get_page_data

    with pytest.raises(ApplicationError):
        await get_page_data("does-not-exist")
