"""Contract tests - what a query returns, the same on every backend.

One fixed dataset (``ContractItem`` + ``ContractGroup``) and cases written as
the contract - expected by hand, not taken from whatever one backend returns.
CI runs the suite on SQLite and PostgreSQL (``TEST_DATABASE_URL``), so every
case holds on both. See DB_LAYERS_PLAN.md, step 2.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest_asyncio

PERMS = [{"role": "All", "actions": ["read", "write", "create", "delete"]}]

GROUP = {
    "name": "ContractGroup",
    "label": "Contract Group",
    "module": "test",
    "autoname": "prompt",
    "title_field": "label",
    "fields": [{"fieldname": "label", "label": "Label", "fieldtype": "Data"}],
    "permissions": PERMS,
}

ITEM = {
    "name": "ContractItem",
    "label": "Contract Item",
    "module": "test",
    "autoname": "prompt",
    "title_field": "title",
    "search_fields": ["title", "note", "grp"],
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "note", "label": "Note", "fieldtype": "Data"},
        {"fieldname": "qty", "label": "Qty", "fieldtype": "Int"},
        {"fieldname": "price", "label": "Price", "fieldtype": "Currency"},
        {"fieldname": "done", "label": "Done", "fieldtype": "Check"},
        {"fieldname": "due", "label": "Due", "fieldtype": "Date"},
        {"fieldname": "at", "label": "At", "fieldtype": "Datetime"},
        {"fieldname": "kind", "label": "Kind", "fieldtype": "Select", "options": "A\nB\nC"},
        {"fieldname": "grp", "label": "Group", "fieldtype": "Link", "options": "ContractGroup"},
        {
            "fieldname": "tags",
            "label": "Tags",
            "fieldtype": "MultiLink",
            "options": "ContractGroup",
        },
    ],
    "permissions": PERMS,
}

GROUPS = {"G1": "Перша група", "G2": "Друга група", "G3": "Третя група"}


def _at(day: str, hour: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=UTC)


# name: (title, note, qty, price, done, due, at, kind, grp, tags)
ROWS = {
    "C01": (
        "Ґанок",
        "50% знижка",
        5,
        Decimal("10.50"),
        True,
        date(2026, 1, 15),
        _at("2026-01-15", 9),
        "A",
        "G1",
        ["G1", "G2"],
    ),
    "C02": (
        "Гарбуз",
        "snake_case",
        3,
        Decimal("99.99"),
        False,
        date(2026, 4, 1),
        _at("2026-04-01", 12),
        "B",
        "G2",
        ["G2"],
    ),
    "C03": ("Єнот", "", None, Decimal("0"), False, None, None, "A", None, []),
    "C04": (
        "Ехо",
        None,
        10,
        Decimal("5.25"),
        True,
        date(2025, 12, 31),
        _at("2025-12-31", 23),
        "C",
        "G1",
        [],
    ),
    "C05": (
        "Іскра",
        "Іскра в ночі",
        7,
        None,
        False,
        date(2026, 7, 4),
        _at("2026-07-04", 6),
        "B",
        "G3",
        ["G3"],
    ),
    "C06": (
        "Їжак",
        "лісовий звір",
        0,
        Decimal("1.00"),
        True,
        date(2026, 10, 10),
        _at("2026-10-10", 15),
        "A",
        "G2",
        ["G1"],
    ),
    "C07": (
        "Иній",
        "ранковий",
        2,
        Decimal("2.00"),
        False,
        date(2026, 1, 1),
        _at("2026-01-01", 0),
        None,
        None,
        [],
    ),
    "C08": (
        "абрикос",
        "fruit",
        4,
        Decimal("3.30"),
        True,
        date(2026, 3, 20),
        _at("2026-03-20", 8),
        "C",
        "G3",
        [],
    ),
    "C09": (
        "Яблуко",
        "fruit",
        12,
        Decimal("4.40"),
        False,
        date(2026, 9, 1),
        _at("2026-09-01", 18),
        "B",
        "G1",
        ["G3"],
    ),
    "C10": (
        "zebra",
        "ZEBRA crossing",
        1,
        Decimal("7.70"),
        False,
        date(2026, 6, 30),
        _at("2026-06-30", 21),
        "C",
        "G2",
        [],
    ),
}
ALL = set(ROWS)

#: Titles in text order: case ignored, then Unicode code points - no language
#: rules (so Є, І, Ї, Ґ come after Я: U+0454, U+0456, U+0457, U+0491).
TEXT_ORDER = [
    "zebra",
    "абрикос",
    "Гарбуз",
    "Ехо",
    "Иній",
    "Яблуко",
    "Єнот",
    "Іскра",
    "Їжак",
    "Ґанок",
]


@pytest_asyncio.fixture
async def dataset(ctx):
    """Both DocTypes, synced, with the rows above."""
    from grunt.api.v1.meta import save_doctype, sync_doctype

    for dt in (GROUP, ITEM):
        await save_doctype(doctype_data={**dt, "__is_new": True})
        await sync_doctype(name=dt["name"])
    for name, label in GROUPS.items():
        await ctx.new_doc("ContractGroup", {"name": name, "label": label})
    fields = ("title", "note", "qty", "price", "done", "due", "at", "kind", "grp", "tags")
    for name, values in ROWS.items():
        await ctx.new_doc("ContractItem", {"name": name, **dict(zip(fields, values, strict=True))})
    await ctx.db._session().commit()
    return ROWS
