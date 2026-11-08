"""Virtual DocTypes filter, sort and search their rows in memory
(:class:`grunt.store.VirtualStore`) - the same contract as SQL, on the rows a
list returns.

MultiLink filters and Link-by-title search need the database; they're SQL-only.
"""

from typing import Any

import pytest

from grunt.query.parse import parse_filters
from grunt.query.query import Query, Sort
from grunt.query.sql import filter_expr
from grunt.store import VirtualStore

from .conftest import TEXT_ORDER
from .test_filters import CASES

ROW_FIELDS = ["name", "title", "note", "qty", "price", "done", "due", "at", "kind", "grp"]
SQL_ONLY = ("tags",)


class _RowsStore(VirtualStore):
    def __init__(self, meta: Any, session: Any, rows: list[dict[str, Any]]) -> None:
        super().__init__(meta, session)
        self._rows = rows

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        return self._rows


@pytest.fixture
async def store(ctx, dataset):
    """A virtual store holding the rows as a list returns them."""
    result = await ctx.get_list("ContractItem", fields=ROW_FIELDS, limit=100)
    meta = await ctx.get_meta("ContractItem")
    return _RowsStore(meta, ctx.get_session(), [dict(r) for r in result])


async def _names(store: _RowsStore, **query: Any) -> list[str]:
    return [r["name"] for r in await store.fetch(Query("ContractItem", **query))]


IN_MEMORY_CASES = [c for c in CASES if not any(k.split("__")[0] in SQL_ONLY for k in c[0])]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    IN_MEMORY_CASES,
    ids=[",".join(f"{k}={v!r}" for k, v in c[0].items()) for c in IN_MEMORY_CASES],
)
async def test_filter_in_memory(store, case):
    filters, expected = case
    where = filter_expr(filters, store.meta.columns, store.meta)
    assert set(await _names(store, where=where)) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_sort_in_memory_like_sql(store, order):
    query = Query("ContractItem", sort=Sort("title", descending=order == "desc"))
    titles = [r["title"] for r in await store.fetch(query)]
    assert titles == (TEXT_ORDER if order == "asc" else TEXT_ORDER[::-1])


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize(("field", "empty"), [("qty", "C03"), ("due", "C03"), ("price", "C05")])
async def test_sort_in_memory_empties_last(store, field, order, empty):
    sorted_rows = await store.fetch(
        Query("ContractItem", sort=Sort(field, descending=order == "desc"))
    )
    assert sorted_rows[-1]["name"] == empty
    values = [r[field] for r in sorted_rows[:-1]]
    assert values == sorted(values, reverse=order == "desc")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("q", "expected"),
    [("ґанок", {"C01"}), ("Іскра ночі", {"C05"}), ("50%", {"C01"}), ("_", {"C02"})],
)
async def test_search_in_memory(store, q, expected):
    assert set(await _names(store, search=q)) == expected


@pytest.mark.asyncio
async def test_pages_in_memory_like_sql(store):
    """Offset and keyset pages walk the same order without gaps or repeats."""
    order = Sort("qty", descending=False)
    every = await _names(store, sort=order)
    assert await _names(store, sort=order, limit=3, offset=3) == every[3:6]
    first = await store.fetch(Query("ContractItem", sort=order, limit=3))
    after = (first[-1]["qty"], first[-1]["name"])
    assert await _names(store, sort=order, limit=3, after=after) == every[3:6]


def test_like_wildcards_take_linear_time():
    """A filter value is user input: many % on a long row must not backtrack
    exponentially (a regex of .* groups did) and block the worker."""
    import time

    from grunt.query.evaluate import matches

    row = {"name": "x", "note": "a" * 5000}
    started = time.perf_counter()
    assert not matches(parse_filters({"note__ilike": "a%" * 30 + "b"}), row)
    assert time.perf_counter() - started < 1
