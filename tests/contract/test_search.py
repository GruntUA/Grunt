"""Search: the list's search box and the global (full-text) search.

List search - every term must be found in some searched field, case ignored,
``%``/``_`` literal, a Link field matched by the linked record's title.
Global search - every term as a word prefix (FTS5 / tsvector / LIKE fallback).
"""

import pytest

LIST_CASES: list[tuple[str, set[str]]] = [
    ("ґанок", {"C01"}),  # Cyrillic, case ignored
    ("ЯБЛУКО", {"C09"}),
    ("Іскра ночі", {"C05"}),  # terms in different fields
    ("ночі Іскра", {"C05"}),  # in any order
    ("Друга", {"C02", "C06", "C10"}),  # Link: by the group's title, not its id
    ("fruit", {"C08", "C09"}),
    ("zebra cross", {"C10"}),
    ("50%", {"C01"}),  # % is a character, not a wildcard
    ("_", {"C02"}),  # so is _
    ("неіснуюче", set()),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("q", "expected"), LIST_CASES, ids=[c[0] for c in LIST_CASES])
async def test_list_search(ctx, dataset, q, expected):
    rows = await ctx.get_list("ContractItem", search=q, fields=["name"], limit=100)
    assert {r["name"] for r in rows} == expected
    assert rows.meta["total"] == len(expected)


GLOBAL_CASES: list[tuple[str, set[str]]] = [
    ("Ґанок", {"C01"}),
    ("ґан", {"C01"}),  # a word prefix, case ignored
    ("Іскр", {"C05"}),
    ("ZEBRA", {"C10"}),
    ("Ехо", {"C04"}),
    ("%%", set()),  # nothing to search for
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("q", "expected"), GLOBAL_CASES, ids=[c[0] for c in GLOBAL_CASES])
async def test_global_search(ctx, dataset, q, expected):
    from grunt.api.v1.search import global_search

    found = {r["name"] for r in await global_search(q=q) if r["doctype"] == "ContractItem"}
    assert found == expected
