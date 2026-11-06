"""Virtual DocTypes filter and sort their rows in memory (grunt.document.in_memory)
- the same contract as SQL, on the rows a list returns.

MultiLink filters and Link-by-title search need the database; they're SQL-only.
"""

import pytest

from grunt.document.in_memory import apply_filters, apply_search, apply_sort

from .conftest import TEXT_ORDER
from .test_filters import CASES

ROW_FIELDS = ["name", "title", "note", "qty", "price", "done", "due", "at", "kind", "grp"]
SQL_ONLY = ("tags",)


@pytest.fixture
async def rows(ctx, dataset):
    """The rows as a list returns them - what a virtual DocType's controller holds."""
    result = await ctx.get_list("ContractItem", fields=ROW_FIELDS, limit=100)
    return [dict(r) for r in result]


IN_MEMORY_CASES = [c for c in CASES if not any(k.split("__")[0] in SQL_ONLY for k in c[0])]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    IN_MEMORY_CASES,
    ids=[",".join(f"{k}={v!r}" for k, v in c[0].items()) for c in IN_MEMORY_CASES],
)
async def test_filter_in_memory(rows, case):
    filters, expected = case
    assert {r["name"] for r in apply_filters(rows, filters)} == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_sort_in_memory_like_sql(rows, order):
    titles = [r["title"] for r in apply_sort(rows, "title", order)]
    assert titles == (TEXT_ORDER if order == "asc" else TEXT_ORDER[::-1])


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize(("field", "empty"), [("qty", "C03"), ("due", "C03"), ("price", "C05")])
async def test_sort_in_memory_empties_last(rows, field, order, empty):
    sorted_rows = apply_sort(rows, field, order)
    assert sorted_rows[-1]["name"] == empty
    values = [r[field] for r in sorted_rows[:-1]]
    assert values == sorted(values, reverse=order == "desc")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("q", "expected"),
    [("ґанок", {"C01"}), ("Іскра ночі", {"C05"}), ("50%", {"C01"}), ("_", {"C02"})],
)
async def test_search_in_memory(rows, q, expected):
    found = apply_search(rows, q, ["title", "note"])
    assert {r["name"] for r in found} == expected
