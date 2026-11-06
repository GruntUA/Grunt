"""Aggregates: GROUP BY a field or a date bucket, count/sum/avg/min/max.

Date buckets of a Datetime are taken in UTC - every datetime in Grunt is UTC,
whatever time zone the database session happens to be in.
"""

import pytest

MISSING = object()


async def _groups(ctx, group_by: str, aggregations: dict[str, str], **kwargs) -> dict:
    rows = await ctx.db.aggregate(
        "ContractItem", group_by=group_by, aggregations=aggregations, **kwargs
    )
    return {r[group_by]: {k: r[k] for k in aggregations} for r in rows}


def _num(value):
    return None if value is None else float(value)


@pytest.mark.asyncio
async def test_group_by_field_count_sum_avg(ctx, dataset):
    groups = await _groups(
        ctx,
        "kind",
        {"n": "count()", "qty": "sum(qty)", "avg_qty": "avg(qty)", "price": "sum(price)"},
    )
    assert {k: v["n"] for k, v in groups.items()} == {"A": 3, "B": 3, "C": 3, None: 1}
    assert {k: _num(v["qty"]) for k, v in groups.items()} == {"A": 5, "B": 22, "C": 15, None: 2}
    avg = {k: _num(v["avg_qty"]) for k, v in groups.items()}
    assert avg == pytest.approx({"A": 2.5, "B": 22 / 3, "C": 5, None: 2})  # NULL qty skipped
    price = {k: _num(v["price"]) for k, v in groups.items()}
    assert price == pytest.approx({"A": 11.5, "B": 104.39, "C": 16.25, None: 2.0})


@pytest.mark.asyncio
async def test_min_max_of_a_date(ctx, dataset):
    groups = await _groups(ctx, "kind", {"first": "min(due)", "last": "max(due)"})
    as_text = {k: (str(v["first"])[:10], str(v["last"])[:10]) for k, v in groups.items()}
    assert as_text["A"] == ("2026-01-15", "2026-10-10")  # NULL due (C03) ignored
    assert as_text["C"] == ("2025-12-31", "2026-06-30")


@pytest.mark.asyncio
async def test_groups_follow_the_sort_rule(ctx, dataset):
    rows = await ctx.db.aggregate(
        "ContractItem", group_by="kind", aggregations={"n": "count()"}, order_by="kind", order="asc"
    )
    assert [r["kind"] for r in rows] == ["A", "B", "C", None]  # empty group last
    rows = await ctx.db.aggregate(
        "ContractItem",
        group_by="kind",
        aggregations={"n": "count()"},
        order_by="kind",
        order="desc",
    )
    assert [r["kind"] for r in rows] == ["C", "B", "A", None]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("group_by", "expected"),
    [
        (
            "month(due)",
            {
                "2025-12": 1,
                "2026-01": 2,
                "2026-03": 1,
                "2026-04": 1,
                "2026-06": 1,
                "2026-07": 1,
                "2026-09": 1,
                "2026-10": 1,
                None: 1,
            },
        ),
        (
            "quarter(due)",
            {"2025-Q4": 1, "2026-Q1": 3, "2026-Q2": 2, "2026-Q3": 2, "2026-Q4": 1, None: 1},
        ),
        ("year(due)", {"2025": 1, "2026": 8, None: 1}),
        # Datetime buckets are UTC: 2025-12-31 23:00 and 2026-01-01 00:00 UTC stay put
        ("year(at)", {"2025": 1, "2026": 8, None: 1}),
        (
            "day(at)",
            {
                "2025-12-31": 1,
                "2026-01-01": 1,
                "2026-01-15": 1,
                "2026-03-20": 1,
                "2026-04-01": 1,
                "2026-06-30": 1,
                "2026-07-04": 1,
                "2026-09-01": 1,
                "2026-10-10": 1,
                None: 1,
            },
        ),
    ],
)
async def test_date_buckets(ctx, dataset, group_by, expected):
    groups = await _groups(ctx, group_by, {"n": "count()"})
    assert {k: v["n"] for k, v in groups.items()} == expected


@pytest.mark.asyncio
async def test_filters_apply_before_grouping(ctx, dataset):
    groups = await _groups(ctx, "kind", {"n": "count()"}, filters={"done": 1})
    assert {k: v["n"] for k, v in groups.items()} == {"A": 2, "C": 2}
