"""Filters: every operator, on every kind of field, with NULL and ''.

``like``/``ilike``/``nlike`` take a pattern: ``%`` and ``_`` are wildcards.

SQL semantics where it matters: a comparison never matches NULL (``ne``,
``nin``, ``gt``...), ``__is not set`` / ``lte_or_null`` / ``nlike`` are the
operators that do.
"""

from datetime import UTC, date, datetime

import pytest

from .conftest import ALL

CASES: list[tuple[dict, set[str]]] = [
    # Data
    ({"title": "Ехо"}, {"C04"}),
    ({"title": "zebra"}, {"C10"}),
    ({"title__ne": "Ехо"}, ALL - {"C04"}),
    ({"title__ilike": "ЕХО"}, {"C04"}),  # Cyrillic, case ignored
    ({"title__ilike": "ЇЖ"}, {"C06"}),
    ({"note__ilike": "fruit"}, {"C08", "C09"}),
    ({"note__ilike": "zebra"}, {"C10"}),  # Latin, case ignored
    ({"note__nlike": "fruit"}, ALL - {"C08", "C09"}),  # NULL note (C04) matches
    # A filter value is a LIKE pattern - apps pass their own "%...%" - unlike
    # what a person types into a search box (see test_search.py)
    ({"note__ilike": "s_ake"}, {"C02"}),
    ({"title__ilike": "%ехо%"}, {"C04"}),
    ({"note__ilike": "50%"}, {"C01"}),
    ({"note__like": "zebra"}, {"C10"}),  # like ignores case too, on every backend
    ({"note__is": "set"}, ALL - {"C03", "C04"}),  # '' and NULL are both "not set"
    ({"note__is": "not set"}, {"C03", "C04"}),
    # Int
    ({"qty": 0}, {"C06"}),
    ({"qty__gt": 5}, {"C04", "C05", "C09"}),
    ({"qty__gte": 7}, {"C04", "C05", "C09"}),
    ({"qty__lt": 2}, {"C06", "C10"}),
    ({"qty__lte": 2}, {"C06", "C07", "C10"}),  # NULL (C03) is not <= 2
    ({"qty__lte_or_null": 2}, {"C03", "C06", "C07", "C10"}),
    ({"qty__isnull": True}, {"C03"}),
    ({"qty__isnull": False}, ALL - {"C03"}),
    ({"qty__in": [0, 1, 12]}, {"C06", "C10", "C09"}),
    ({"qty__in": "0, 1, 12"}, {"C06", "C10", "C09"}),  # CSV, as from a query string
    ({"qty__gt": "5"}, {"C04", "C05", "C09"}),  # a number as a query-string value
    # Currency
    ({"price": 0}, {"C03"}),
    ({"price__gt": 5}, {"C01", "C02", "C04", "C10"}),
    ({"price__gt": "5"}, {"C01", "C02", "C04", "C10"}),
    ({"price__is": "not set"}, {"C05"}),
    # Check - bool, 1/0 and their strings alike
    ({"done": True}, {"C01", "C04", "C06", "C08"}),
    ({"done": 1}, {"C01", "C04", "C06", "C08"}),
    ({"done": "1"}, {"C01", "C04", "C06", "C08"}),
    ({"done": False}, ALL - {"C01", "C04", "C06", "C08"}),
    ({"done": "0"}, ALL - {"C01", "C04", "C06", "C08"}),
    # Date - a date or its ISO string
    ({"due": date(2026, 1, 15)}, {"C01"}),
    ({"due": "2026-01-15"}, {"C01"}),
    ({"due__gte": "2026-07-01"}, {"C05", "C06", "C09"}),
    ({"due__lt": date(2026, 1, 15)}, {"C04", "C07"}),
    ({"due__year": 2026}, ALL - {"C03", "C04"}),
    ({"due__year": "2025"}, {"C04"}),
    ({"due__year": "not a year"}, set()),
    ({"due__is": "not set"}, {"C03"}),
    # Datetime (UTC)
    ({"at__gte": datetime(2026, 10, 10, 15, tzinfo=UTC)}, {"C06"}),
    ({"at__gte": "2026-10-10T15:00:00+00:00"}, {"C06"}),
    ({"at__year": 2025}, {"C04"}),
    # Select
    ({"kind": "A"}, {"C01", "C03", "C06"}),
    ({"kind__ne": "A"}, {"C02", "C04", "C05", "C08", "C09", "C10"}),  # NULL (C07) excluded
    ({"kind__in": ["A", "C"]}, {"C01", "C03", "C04", "C06", "C08", "C10"}),
    ({"kind__nin": ["A", "C"]}, {"C02", "C05", "C09"}),  # NULL (C07) excluded
    ({"kind__is": "not set"}, {"C07"}),
    # Link
    ({"grp": "G1"}, {"C01", "C04", "C09"}),
    ({"grp__is": "not set"}, {"C03", "C07"}),
    # MultiLink
    ({"tags": "G1"}, {"C01", "C06"}),
    ({"tags__in": ["G2", "G3"]}, {"C01", "C02", "C05", "C09"}),
    ({"tags__nin": ["G1"]}, ALL - {"C01", "C06"}),
    ({"tags__is": "set"}, {"C01", "C02", "C05", "C06", "C09"}),
    ({"tags__is": "not set"}, {"C03", "C04", "C07", "C08", "C10"}),
    # Combined - ANDed
    ({"kind": "A", "done": True}, {"C01", "C06"}),
    ({"grp": "G1", "due__year": 2026}, {"C01", "C09"}),
]


def _id(case: tuple[dict, set[str]]) -> str:
    return ",".join(f"{k}={v!r}" for k, v in case[0].items())


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[_id(c) for c in CASES])
async def test_filter(ctx, dataset, case):
    filters, expected = case
    rows = await ctx.get_list("ContractItem", filters=filters, fields=["name"], limit=100)
    assert {r["name"] for r in rows} == expected
    assert await ctx.count("ContractItem", filters=filters) == len(expected)
