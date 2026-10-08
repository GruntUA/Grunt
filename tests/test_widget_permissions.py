"""Dashboard widgets compute as the viewer: no numbers about rows they cannot read."""

from __future__ import annotations

import pytest

from tests.test_aggregate import ALICE, as_user, deals  # noqa: F401  (fixtures)


def _widget(widget_type: str, **kwargs) -> dict:
    return {
        "name": f"w-{widget_type}",
        "widget_type": widget_type,
        "ref_doctype": "AggDeal",
        "period": "last_month",
        **kwargs,
    }


async def _compute(widget):
    from grunt.api.v1.dashboard import _compute_widget_data

    return await _compute_widget_data(widget)


@pytest.mark.asyncio
async def test_row_level_rules_shape_every_widget(deals, as_user):  # noqa: F811
    async with as_user("admin@grunt.example.com", ["System Manager"]):
        assert (await _compute(_widget("metric", aggregation="count")))["value"] == 4
        assert (await _compute(_widget("shortcut")))["count"] == 4

    async with as_user(ALICE, ["Seller"]):  # sees only her own 3 deals
        assert (await _compute(_widget("metric", aggregation="count")))["value"] == 3
        metric = await _compute(_widget("metric", aggregation="sum", field="amount"))
        assert metric["value"] == 400.0
        assert (await _compute(_widget("shortcut")))["count"] == 3

        donut = await _compute(_widget("donut", group_by="status"))
        assert dict(zip(donut["labels"], donut["values"], strict=True)) == {"Won": 2, "Open": 1}

        table = await _compute(
            _widget("table", group_by="status", aggregation="sum", field="amount")
        )
        assert {r["label"]: r["value"] for r in table["rows"]} == {"Won": 300.0, "Open": 100.0}


@pytest.mark.asyncio
async def test_hidden_fields_and_no_access(deals, as_user):  # noqa: F811
    async with as_user(ALICE, ["Seller"]):
        # "cost" is permission-hidden for Sellers -> the widget stays empty.
        hidden = await _compute(_widget("metric", aggregation="sum", field="cost"))
        assert hidden["value"] == 0
        table = await _compute(_widget("table", group_by="cost"))
        assert table["rows"] == []

    async with as_user("nobody@grunt.example.com", []):
        assert await _compute(_widget("metric", aggregation="count")) is None
        assert await _compute(_widget("shortcut")) is None
