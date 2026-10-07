"""Fixture export (``grunt fixtures export``) and sync-mode loading.

Export turns DB records into portable fixture JSON; a ``"sync": true`` file
updates existing records on load, a plain seed file only inserts missing ones.
"""

from __future__ import annotations

import json

import pytest

_PARENT = {
    "name": "FxConfig",
    "label": "Fx Config",
    "module": "core",
    "autoname": "field:code",
    "fields": [
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": True},
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "limit_qty", "label": "Limit", "fieldtype": "Int"},
        {"fieldname": "secret", "label": "Secret", "fieldtype": "Password"},
        {"fieldname": "rows", "label": "Rows", "fieldtype": "Table", "options": "FxConfigRow"},
    ],
}

_CHILD = {
    "name": "FxConfigRow",
    "label": "Fx Config Row",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "label", "label": "Label", "fieldtype": "Data"},
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Int"},
    ],
}


@pytest.fixture
async def fx_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_CHILD, "__is_new": True})
    await save_doctype(doctype_data={**_PARENT, "__is_new": True})
    await ctx.db._session().commit()


async def _make(ctx, code: str = "alpha", **extra):
    doc = await ctx.new_doc(
        "FxConfig",
        {
            "code": code,
            "title": "Alpha",
            "limit_qty": 5,
            "secret": "hunter2",
            "rows": [{"label": "a", "amount": 1}, {"label": "b", "amount": 2}],
            **extra,
        },
    )
    await ctx.db._session().commit()
    return doc


def test_parse_fixture_specs():
    from grunt.fixtures import FixtureSpec, parse_fixture_specs

    specs = parse_fixture_specs(
        ["Role", {"doctype": "Page", "filters": {"name": "x"}, "file": "01_page.json"}]
    )
    assert specs == [
        FixtureSpec("Role"),
        FixtureSpec("Page", {"name": "x"}, "01_page.json"),
    ]
    assert specs[0].filename == "role.json"
    with pytest.raises(ValueError):
        parse_fixture_specs([{"filters": {}}])


@pytest.mark.asyncio
async def test_export_strips_system_and_password_fields(ctx, fx_doctype, tmp_path):
    from grunt.fixtures import FixtureSpec, export_fixtures

    doc = await _make(ctx)
    [(path, count)] = await export_fixtures([FixtureSpec("FxConfig")], tmp_path)

    assert count == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["doctype"] == "FxConfig"
    assert data["sync"] is True
    [rec] = data["records"]
    assert rec == {
        "name": doc["name"],
        "code": "alpha",
        "title": "Alpha",
        "limit_qty": 5,
        "rows": [
            {"doctype": "FxConfigRow", "label": "a", "amount": 1},
            {"doctype": "FxConfigRow", "label": "b", "amount": 2},
        ],
    }


@pytest.mark.asyncio
async def test_export_respects_filters(ctx, fx_doctype, tmp_path):
    from grunt.fixtures import FixtureSpec, export_records

    await _make(ctx, "alpha")
    await _make(ctx, "beta")
    records = await export_records(FixtureSpec("FxConfig", {"code": "beta"}))
    assert [r["code"] for r in records] == ["beta"]


@pytest.mark.asyncio
async def test_sync_fixture_updates_existing_record(ctx, fx_doctype, db_session, engine):
    from grunt.fixtures import FixtureSpec, export_records
    from grunt.startup.fixtures import _apply_doctype_fixture

    doc = await _make(ctx)
    [rec] = await export_records(FixtureSpec("FxConfig"))
    rec["title"] = "Changed"
    rec["rows"] = [{"label": "z", "amount": 9}]

    await _apply_doctype_fixture("FxConfig", [rec], db_session, engine, sync=True)
    await db_session.commit()

    fresh = await ctx.get_doc("FxConfig", doc["name"])
    assert fresh["title"] == "Changed"
    assert fresh["limit_qty"] == 5
    assert [(r["label"], r["amount"]) for r in fresh["rows"]] == [("z", 9)]


@pytest.mark.asyncio
async def test_seed_fixture_does_not_touch_existing_record(ctx, fx_doctype, db_session, engine):
    from grunt.startup.fixtures import _apply_doctype_fixture

    doc = await _make(ctx)
    rec = {"name": doc["name"], "code": "alpha", "title": "Changed"}

    await _apply_doctype_fixture("FxConfig", [rec], db_session, engine)
    await db_session.commit()

    assert (await ctx.get_doc("FxConfig", doc["name"]))["title"] == "Alpha"


@pytest.mark.asyncio
async def test_unchanged_sync_fixture_is_not_resaved(ctx, fx_doctype, db_session, engine):
    from grunt.fixtures import FixtureSpec, export_records
    from grunt.startup.fixtures import _apply_doctype_fixture

    doc = await _make(ctx)
    before = (await ctx.get_doc("FxConfig", doc["name"]))["modified_at"]
    records = await export_records(FixtureSpec("FxConfig"))

    await _apply_doctype_fixture("FxConfig", records, db_session, engine, sync=True)
    await db_session.commit()

    assert (await ctx.get_doc("FxConfig", doc["name"]))["modified_at"] == before


@pytest.mark.asyncio
async def test_sync_fixture_inserts_missing_record(ctx, fx_doctype, db_session, engine):
    from grunt.startup.fixtures import _apply_doctype_fixture

    rec = {"name": "gamma", "code": "gamma", "title": "G", "rows": [{"label": "x", "amount": 3}]}
    await _apply_doctype_fixture("FxConfig", [rec], db_session, engine, sync=True)
    await db_session.commit()

    fresh = await ctx.get_doc("FxConfig", "gamma")
    assert fresh["title"] == "G"
    assert [r["label"] for r in fresh["rows"]] == ["x"]


@pytest.mark.asyncio
async def test_sync_fixture_leaves_matching_record_alone(ctx, fx_doctype, db_session, engine):
    """Child rows compare on the fixture's keys - a stored row also holds empty fillers."""
    from grunt.startup.fixtures import _apply_doctype_fixture

    doc = await _make(ctx)
    before = (await ctx.get_doc("FxConfig", doc["name"]))["modified_at"]
    rec = {"name": doc["name"], "code": "alpha", "rows": [{"label": "a"}, {"label": "b"}]}

    await _apply_doctype_fixture("FxConfig", [rec], db_session, engine, sync=True)
    await db_session.commit()

    assert (await ctx.get_doc("FxConfig", doc["name"]))["modified_at"] == before
