"""Sorting and paging: text case ignored, NULLs last, stable pages."""

import pytest

from .conftest import ROWS, TEXT_ORDER

TITLE = {name: row[0] for name, row in ROWS.items()}


async def _titles(ctx, **kwargs) -> list[str]:
    rows = await ctx.get_list("ContractItem", fields=["name"], limit=100, **kwargs)
    return [TITLE[r["name"]] for r in rows]


@pytest.mark.asyncio
async def test_text_sorts_case_ignored_by_code_point(ctx, dataset):
    # Case ignored ("абрикос" among capitals), then code points - the same on
    # every backend and in memory
    assert await _titles(ctx, order_by="title", order="asc") == TEXT_ORDER
    assert await _titles(ctx, order_by="title", order="desc") == TEXT_ORDER[::-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize(
    ("field", "empty"),
    [("qty", {"C03"}), ("due", {"C03"}), ("price", {"C05"}), ("kind", {"C07"})],
)
async def test_empty_values_go_last_both_ways(ctx, dataset, field, order, empty):
    rows = await ctx.get_list(
        "ContractItem", fields=["name", field], limit=100, order_by=field, order=order
    )
    names = [r["name"] for r in rows]
    assert set(names[-len(empty) :]) == empty
    values = [r[field] for r in rows[: -len(empty)]]
    assert values == sorted(values, reverse=order == "desc")


@pytest.mark.asyncio
async def test_pages_join_into_the_whole_list(ctx, dataset):
    whole = await _titles(ctx, order_by="title", order="asc")
    paged: list[str] = []
    for page in range(1, 5):
        result = await ctx.get_list(
            "ContractItem", fields=["name"], limit=3, page=page, order_by="title", order="asc"
        )
        paged += [TITLE[r["name"]] for r in result]
    assert paged == whole
    first = await ctx.get_list("ContractItem", fields=["name"], limit=3, page=1)
    assert first.meta["total"] == len(ROWS)


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("field", ["title", "qty", "due", "kind", "name"])
async def test_cursor_pages_join_into_the_whole_list(ctx, dataset, field, order):
    """Keyset paging follows the same order - text case ignored, empties last."""
    kwargs = {"fields": ["name", field], "order_by": field, "order": order}
    whole = [r["name"] for r in await ctx.get_list("ContractItem", limit=100, **kwargs)]
    paged: list[str] = []
    cursor = None
    for _ in range(10):
        result = await ctx.get_list("ContractItem", limit=3, cursor=cursor, **kwargs)
        paged += [r["name"] for r in result]
        cursor = result.meta["next_cursor"]
        if cursor is None:
            break
    assert paged == whole
