"""List reports: fixed conditions, date grouping, sort + top N."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

SALE = {
    "name": "RptSale",
    "label": "Rpt Sale",
    "module": "core",
    "fields": [
        {"fieldname": "region", "label": "Region", "fieldtype": "Data"},
        {"fieldname": "sold_on", "label": "Sold on", "fieldtype": "Date"},
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Float"},
    ],
    "permissions": [{"role": "System Manager", "read": True, "create": True}],
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
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**SALE, "__is_new": True})
    for region, sold_on, amount in ROWS:
        await ctx.new_doc("RptSale", {"region": region, "sold_on": sold_on, "amount": amount})
    await ctx.db._session().commit()


async def _run(ctx, **report):
    from grunt.reports.engine import report_engine

    return await report_engine._run_list_report(
        "RptSale", report, {}, ctx.get_user(), ctx.db._session()
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
