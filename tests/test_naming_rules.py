"""Naming beyond a fixed series: fields and the document's date in the name,
the local date, ``naming_series:``, Document Naming Rules, skipping taken
names, the counter API (FRAPPE_GAP_PLAN #17)."""

from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException

from grunt.errors import ApplicationError
from grunt.naming.patterns import (
    MissingFieldValueError,
    build_prefix,
    field_tokens,
    format_name,
    parse_pattern,
)

ERRORS = (ApplicationError, HTTPException)

BOX = {
    "name": "NameBox",
    "label": "Name Box",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "dept", "label": "Department", "fieldtype": "Data"},
        {"fieldname": "received_on", "label": "Received on", "fieldtype": "Date"},
        {
            "fieldname": "naming_series",
            "label": "Series",
            "fieldtype": "Select",
            "options": "NB-.###\nNX-.YY.-.###",
        },
    ],
    "permissions": [{"role": "System Manager", "actions": ["read", "create", "write", "delete"]}],
}


async def _box(ctx, **extra):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, **extra, "__is_new": True})
    await ctx.db._session().commit()
    return await ctx.get_meta("NameBox")


async def _new(ctx, **data) -> str:
    return (await ctx.new_doc("NameBox", {"title": "t", **data}))["name"]


async def _rule(ctx, autoname: str, condition: str = "", priority: int = 0, **extra) -> str:
    doc = await ctx.new_doc(
        "DocumentNamingRule",
        {
            "document_type": "NameBox",
            "autoname": autoname,
            "condition": condition,
            "priority": priority,
            **extra,
        },
    )
    await ctx.db._session().commit()
    return doc["name"]


# ── patterns ────────────────────────────────────────────────────────


def test_braced_tokens_and_fields():
    parts = parse_pattern("ВХ-{dept}-{YYYY}-{####}")
    assert parts == ["ВХ-", ("field", "dept"), "-", ("YYYY", 0), "-", ("counter", 4)]
    assert field_tokens(parts) == ["dept"]
    day = date(2026, 11, 21)
    assert build_prefix(parts, now=day, values={"dept": "ЦНАП"}) == "ВХ-ЦНАП-2026-"
    assert format_name(parts, 7, now=day, values={"dept": "ЦНАП"}) == "ВХ-ЦНАП-2026-0007"


def test_dotted_and_braced_mix():
    parts = parse_pattern("X-.YY.-{code}.###")
    assert format_name(parts, 3, now=date(2026, 1, 1), values={"code": "A"}) == "X-26-A003"


def test_empty_field_value_is_refused():
    parts = parse_pattern("ВХ-{dept}-.####")
    with pytest.raises(MissingFieldValueError) as exc:
        build_prefix(parts, now=date(2026, 1, 1), values={"dept": "  "})
    assert exc.value.fieldname == "dept"


# ── dates ───────────────────────────────────────────────────────────


def test_naming_date_is_local(monkeypatch):
    """23:30 UTC on 31 December is already the new year in Kyiv."""
    from grunt.naming.service import local_today

    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 12, 31, 23, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("grunt.naming.service.datetime", _Now)
    assert local_today() == date(2027, 1, 1)


def test_naming_date_from_datetime_field_is_local():
    from grunt.naming.service import naming_date

    class _Dt:
        naming_date_field = "at"

    assert naming_date(_Dt(), {"at": "2026-12-31T23:30:00+00:00"}) == date(2027, 1, 1)
    assert naming_date(_Dt(), {"at": "2026-03-05"}) == date(2026, 3, 5)


@pytest.mark.asyncio
async def test_year_from_the_document_date(ctx):
    await _box(ctx, autoname="NB-.YYYY.-.###", naming_date_field="received_on")
    assert await _new(ctx, received_on="2025-03-01") == "NB-2025-001"
    assert await _new(ctx, received_on="2025-07-01") == "NB-2025-002"
    # Without the date - today's year, its own count.
    assert await _new(ctx) == f"NB-{date.today().year}-001"


# ── fields in the name ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_field_in_the_name_counts_per_value(ctx):
    await _box(ctx, autoname="NB-{dept}-.###")
    assert await _new(ctx, dept="A") == "NB-A-001"
    assert await _new(ctx, dept="B") == "NB-B-001"
    assert await _new(ctx, dept="A") == "NB-A-002"
    with pytest.raises(ERRORS):
        await _new(ctx)


# ── naming_series: ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_naming_series_picked_by_user(ctx):
    await _box(ctx, autoname="naming_series:")
    first = await _new(ctx)
    assert first == "NB-001"
    assert (await ctx.get_doc("NameBox", first))["naming_series"] == "NB-.###"
    assert await _new(ctx, naming_series="NX-.YY.-.###") == f"NX-{date.today():%y}-001"
    with pytest.raises(ERRORS):
        await _new(ctx, naming_series="ZZ-.###")


@pytest.mark.asyncio
async def test_naming_series_ignores_a_caller_supplied_name(ctx):
    await _box(ctx, autoname="naming_series:")
    assert await _new(ctx, name="NB-500") == "NB-001"


# ── Document Naming Rule ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_rule_by_condition_and_priority(ctx):
    await _box(ctx, autoname="NB-.###")
    await _rule(ctx, "LOW-.###", "doc.dept == 'A'", priority=1)
    await _rule(ctx, "HIGH-.###", "doc.dept == 'A' and doc.title == 'vip'", priority=5)
    await _rule(ctx, "OFF-.###", "", priority=99, disabled=1)

    assert await _new(ctx, dept="A") == "LOW-001"
    assert await _new(ctx, dept="A", title="vip") == "HIGH-001"
    assert await _new(ctx, dept="B") == "NB-001"


@pytest.mark.asyncio
async def test_rule_change_takes_effect_and_broken_condition_does_not_match(ctx):
    await _box(ctx, autoname="NB-.###")
    rule = await _rule(ctx, "R-.###", "doc.dept == 'A'")
    assert await _new(ctx, dept="A") == "R-001"

    # Fails at run time -> no match.
    await ctx.save_doc("DocumentNamingRule", rule, {"condition": "doc.missing.attr == 1"})
    await ctx.db._session().commit()
    assert await _new(ctx, dept="A") == "NB-001"


@pytest.mark.asyncio
async def test_rule_validation(ctx):
    await _box(ctx, autoname="NB-.###")
    with pytest.raises(ERRORS):
        await _rule(ctx, "R-.###", "doc.dept ==")  # syntax error
    with pytest.raises(ERRORS):
        await _rule(ctx, "R-{nope}-.###")  # unknown field
    with pytest.raises(ERRORS):
        await _rule(ctx, "naming_series:")


@pytest.mark.asyncio
async def test_rule_beats_the_controller_autoname(ctx, monkeypatch):
    await _box(ctx, autoname="NB-.###")
    await _rule(ctx, "R-.###", "doc.dept == 'A'")

    from grunt.naming.service import naming_service

    async def own(data, session):
        return "OWN"

    calls = []

    async def spy(dt, data, session, **kw):
        calls.append(kw.get("controller_autoname"))
        return await real(dt, data, session, controller_autoname=own)

    real = naming_service.new_name
    monkeypatch.setattr(naming_service, "new_name", spy)
    assert await _new(ctx, dept="A") == "R-001"
    assert await _new(ctx, dept="B") == "OWN"


# ── taken names, counter API ───────────────────────────────────────


@pytest.mark.asyncio
async def test_taken_name_is_skipped(ctx):
    from grunt.api.v1.naming import set_counter

    await _box(ctx, autoname="NB-.###")
    assert await _new(ctx) == "NB-001"
    assert await _new(ctx) == "NB-002"
    await set_counter(prefix="NB-", current=0)
    assert await _new(ctx) == "NB-003"


@pytest.mark.asyncio
async def test_preview_and_counter_api(ctx):
    from grunt.api.v1.naming import counter, preview, set_counter

    await _box(ctx, autoname="NB-.###")
    p = await preview(doctype="NameBox")
    assert (p["prefix"], p["current"], p["next"]) == ("NB-", 0, "NB-001")

    await set_counter(prefix="NB-", current=41)
    assert await counter(prefix="NB-") == 41
    assert (await preview(doctype="NameBox"))["next"] == "NB-042"
    assert await _new(ctx) == "NB-042"

    p = await preview(doctype="NameBox", pattern="NB-{dept}-.###")
    assert p["next"] is None and [f["fieldname"] for f in p["fields"]] == ["dept"]
    p = await preview(doctype="NameBox", pattern="NB-{dept}-.###", doc={"dept": "A"})
    assert p["next"] == "NB-A-001"

    with pytest.raises(ERRORS):
        await set_counter(prefix="NB-", current=-1)


@pytest.mark.asyncio
async def test_app_uninstall_clears_counters_and_rules(ctx):
    from grunt.api.v1.naming import counter, set_counter
    from grunt.cli.app import _delete_naming_series_counters

    meta = await _box(ctx, autoname="NB-{dept}-.###")
    await _rule(ctx, "R-.###", "doc.dept == 'R'")
    await _new(ctx, dept="A")
    await _new(ctx, dept="R")
    await set_counter(prefix="ZZ-", current=5)  # another app's series

    await _delete_naming_series_counters(ctx.db._session(), [meta])

    assert await counter(prefix="NB-A-") == 0
    assert await counter(prefix="R-") == 0
    assert await counter(prefix="ZZ-") == 5
    assert not await ctx.db.exists("DocumentNamingRule", {"document_type": "NameBox"})
