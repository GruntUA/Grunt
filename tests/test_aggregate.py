"""grunt.aggregate - permission-aware GROUP BY, and the MCP ``aggregate`` tool."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from tests.support import make_user

DEAL = {
    "name": "AggDeal",
    "label": "Agg Deal",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "Open\nWon\nLost",
        },
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Float"},
        {"fieldname": "cost", "label": "Cost", "fieldtype": "Float"},
        {"fieldname": "deal_date", "label": "Deal date", "fieldtype": "Date"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Seller", "read": True, "match": "owner == user", "hidden_fields": ["cost"]},
        {"role": "Seller", "create": True},
    ],
}

ALICE = "alice@grunt.example.com"
BOB = "bob@grunt.example.com"

ROWS = [
    (ALICE, "Open", 100.0, 10.0, "2026-01-15"),
    (ALICE, "Won", 250.0, 20.0, "2026-02-03"),
    (ALICE, "Won", 50.0, 5.0, "2026-04-20"),
    (BOB, "Won", 1000.0, 300.0, "2026-02-10"),
]


@pytest.fixture
async def deals(ctx, db_session, engine):
    import grunt
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**DEAL, "__is_new": True})
    for owner, status, amount, cost, when in ROWS:
        async with grunt.context(db_session, engine, make_user(owner, roles=["System Manager"])):
            await grunt.new_doc(
                "AggDeal",
                {
                    "title": f"{owner}-{when}",
                    "status": status,
                    "amount": amount,
                    "cost": cost,
                    "deal_date": when,
                },
            )
    await db_session.commit()


@pytest.fixture
def as_user(db_session, engine):
    import grunt

    def enter(email: str, roles: list[str]):
        return grunt.context(db_session, engine, make_user(email, roles=roles))

    return enter


def _by(rows, key):
    return {r[key]: r for r in rows}


@pytest.mark.asyncio
async def test_group_and_sum_for_full_access(deals, as_user):
    import grunt

    async with as_user("admin@grunt.example.com", ["System Manager"]):
        rows = await grunt.aggregate(
            "AggDeal",
            group_by="status",
            aggregations={"n": "count()", "total": "sum(amount)"},
        )
    by = _by(rows, "status")
    assert (by["Won"]["n"], by["Won"]["total"]) == (3, 1300.0)
    assert (by["Open"]["n"], by["Open"]["total"]) == (1, 100.0)


@pytest.mark.asyncio
async def test_period_buckets(deals, as_user):
    import grunt

    async with as_user("admin@grunt.example.com", ["System Manager"]):
        months = await grunt.aggregate(
            "AggDeal",
            group_by="month(deal_date)",
            aggregations={"total": "sum(amount)"},
            order_by="month(deal_date)",
            order="asc",
        )
        quarters = await grunt.aggregate(
            "AggDeal", group_by=["quarter(deal_date)"], aggregations={"n": "count()"}
        )
        years = await grunt.aggregate("AggDeal", group_by="year(deal_date)")
    assert [(r["month(deal_date)"], r["total"]) for r in months] == [
        ("2026-01", 100.0),
        ("2026-02", 1250.0),
        ("2026-04", 50.0),
    ]
    assert {r["quarter(deal_date)"]: r["n"] for r in quarters} == {"2026-Q1": 3, "2026-Q2": 1}
    assert years == [{"year(deal_date)": "2026", "count": 4}]


@pytest.mark.asyncio
async def test_row_level_rules_apply(deals, as_user):
    import grunt

    async with as_user(ALICE, ["Seller"]):
        rows = await grunt.aggregate(
            "AggDeal", aggregations={"n": "count()", "total": "sum(amount)"}
        )
    assert rows == [{"n": 3, "total": 400.0}]  # Bob's deal is not visible


@pytest.mark.asyncio
async def test_hidden_fields_cannot_be_used(deals, as_user):
    import grunt

    async with as_user(ALICE, ["Seller"]):
        with pytest.raises(HTTPException) as exc:
            await grunt.aggregate("AggDeal", aggregations={"c": "sum(cost)"})
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException):
            await grunt.aggregate("AggDeal", filters={"cost__gt": 1})
        with pytest.raises(HTTPException):
            await grunt.aggregate("AggDeal", group_by="cost")


@pytest.mark.asyncio
async def test_no_read_permission_and_bad_input(deals, as_user):
    import grunt

    async with as_user("nobody@grunt.example.com", []):
        with pytest.raises(HTTPException) as exc:
            await grunt.aggregate("AggDeal")
        assert exc.value.status_code == 403

    async with as_user("admin@grunt.example.com", ["System Manager"]):
        for kwargs in (
            {"group_by": "nope"},
            {"aggregations": {"x": "sum(nope)"}},
            {"aggregations": {"x": "median(amount)"}},
            {"filters": {"nope__gt": 1}},
        ):
            with pytest.raises(HTTPException) as exc:
                await grunt.aggregate("AggDeal", **kwargs)
            assert exc.value.status_code == 422, kwargs


@pytest.mark.asyncio
async def test_mcp_aggregate_tool(deals, db_session, engine):
    import grunt
    from grunt.mcp.protocol import handle_message

    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "aggregate",
            "arguments": {
                "doctype": "AggDeal",
                "group_by": ["status"],
                "filters": {"deal_date__gte": "2026-02-01"},
            },
        },
    }
    async with grunt.context(db_session, engine, make_user(ALICE, roles=["Seller"])):
        result = (await handle_message(msg))["result"]
    assert not result["isError"], result
    rows = json.loads(result["content"][0]["text"])
    assert rows == [{"status": "Won", "count": 2}]
