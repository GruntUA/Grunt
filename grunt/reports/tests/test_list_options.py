"""List reports: fixed conditions, date grouping, sort + top N."""

from datetime import date, timedelta

import pytest

from grunt.api.v1.meta import save_doctype
from grunt.reports.engine import report_engine

SALE = {
    "name": "RptSale",
    "label": "Rpt Sale",
    "module": "core",
    "fields": [
        {"fieldname": "region", "label": "Region", "fieldtype": "Data"},
        {"fieldname": "sold_on", "label": "Sold on", "fieldtype": "Date"},
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Float"},
    ],
    "permissions": [{"role": "System Manager", "actions": ["read", "create"]}],
}

ROWS = [
    ("North", "2026-01-15", 10),
    ("North", "2026-01-20", 5),
    ("South", "2026-02-03", 7),
    ("East", "2026-04-11", 1),
    ("North", "2026-05-01", 2),
]


@pytest.fixture
async def sales(ctx):
    await save_doctype(doctype_data={**SALE, "__is_new": True})
    for region, sold_on, amount in ROWS:
        await ctx.new_doc("RptSale", {"region": region, "sold_on": sold_on, "amount": amount})
    await ctx.db._session().commit()


async def _run(ctx, **report):
    return await report_engine._run_list_report(
        "RptSale", report, {}, ctx.get_user().email, ctx.db._session()
    )


def _col(fieldname, **kw):
    return {"fieldname": fieldname, "label": fieldname, **kw}


@pytest.mark.asyncio
async def test_all_none_aggregations_do_not_group(ctx, sales):
    res = await _run(
        ctx, columns=[_col("region", aggregation="none"), _col("amount", aggregation="none")]
    )
    assert res["meta"]["rows"] == len(ROWS)  # North rows not merged
    assert "drilldown" not in res["meta"]


@pytest.mark.asyncio
async def test_group_by_month_and_quarter(ctx, sales):
    by_month = await _run(
        ctx, columns=[_col("sold_on", date_group="month"), _col("amount", aggregation="sum")]
    )
    assert [(r["sold_on"], r["amount"]) for r in by_month["data"]] == [
        ("2026-01", 15),
        ("2026-02", 7),
        ("2026-04", 1),
        ("2026-05", 2),
    ]
    assert by_month["meta"]["drilldown"]["date_groups"] == {"sold_on": "month"}

    by_quarter = await _run(
        ctx, columns=[_col("sold_on", date_group="quarter"), _col("amount", aggregation="count")]
    )
    assert [(r["sold_on"], r["amount"]) for r in by_quarter["data"]] == [
        ("2026-Q1", 3),
        ("2026-Q2", 2),
    ]


@pytest.mark.asyncio
async def test_conditions_and_top_n(ctx, sales):
    res = await _run(
        ctx,
        columns=[_col("region"), _col("amount", aggregation="sum")],
        conditions=[{"fieldname": "region", "op": "in", "value": "North, South"}],
        sort_by="amount",
        sort_order="desc",
        row_limit=1,
    )
    assert res["data"] == [{"region": "North", "amount": 17}]
    assert res["meta"]["drilldown"]["conditions"] == {"region__in": ["North", "South"]}


@pytest.mark.asyncio
async def test_relative_date_condition(ctx, sales):
    recent = (date.today() - timedelta(days=3)).isoformat()
    await ctx.new_doc("RptSale", {"region": "West", "sold_on": recent, "amount": 4})
    await ctx.db._session().commit()

    res = await _run(
        ctx,
        columns=[_col("region")],
        conditions=[{"fieldname": "sold_on", "op": ">=", "value": "today-7"}],
    )
    assert [r["region"] for r in res["data"]] == ["West"]


@pytest.mark.asyncio
async def test_unknown_sort_column_is_ignored(ctx, sales):
    res = await _run(ctx, columns=[_col("region")], sort_by="region; DROP TABLE x", row_limit=2)
    assert res["meta"]["rows"] == 2


RPT_NODE = {
    "name": "RptNode",
    "label": "Rpt Node",
    "module": "core",
    "is_tree": True,
    "tree_parent_field": "parent_node",
    "tree_title_field": "title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data", "required": True},
        {"fieldname": "parent_node", "label": "Parent", "fieldtype": "Link", "options": "RptNode"},
    ],
    "permissions": [{"role": "System Manager", "actions": ["read", "create"]}],
}

RPT_ITEM = {
    "name": "RptItem",
    "label": "Rpt Item",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "node", "label": "Node", "fieldtype": "Link", "options": "RptNode"},
    ],
    "permissions": [{"role": "System Manager", "actions": ["read", "create"]}],
}


@pytest.mark.asyncio
async def test_child_of_in_filters_and_conditions(ctx):
    """`child_of` narrows a report to the subtree - in the viewer's filters and in
    fixed conditions; drill-down keeps the unexpanded child_of for the list URL."""
    await save_doctype(doctype_data={**RPT_NODE, "__is_new": True})
    await save_doctype(doctype_data={**RPT_ITEM, "__is_new": True})
    root = await ctx.new_doc("RptNode", {"title": "A"})
    child = await ctx.new_doc("RptNode", {"title": "B", "parent_node": root["name"]})
    other = await ctx.new_doc("RptNode", {"title": "C"})
    for title, node in (("in A", root), ("in B", child), ("in C", other)):
        await ctx.new_doc("RptItem", {"title": title, "node": node["name"]})
    await ctx.db._session().commit()

    async def run(report, filters):
        res = await report_engine._run_list_report(
            "RptItem", report, filters, ctx.get_user().email, ctx.db._session()
        )
        return res, sorted(r["title"] for r in res["data"])

    _, titles = await run({"columns": [_col("title")]}, {"node__child_of": root["name"]})
    assert titles == ["in A", "in B"]

    res, _ = await run(
        {
            "columns": [_col("node"), _col("title", aggregation="count")],
            "conditions": [{"fieldname": "node", "op": "child_of", "value": root["name"]}],
        },
        {},
    )
    assert sorted(r["node"] for r in res["data"]) == sorted([root["name"], child["name"]])
    assert res["meta"]["drilldown"]["conditions"] == {"node__child_of": root["name"]}
