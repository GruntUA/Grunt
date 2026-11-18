"""FRAPPE_GAP #4: ``no_copy`` fields stay out of a duplicate, ``set_only_once``
fields can't change once they hold a value."""

import pytest
from fastapi import HTTPException

import grunt
from grunt.api.v1.meta import save_doctype
from tests.support import make_user

LINE = {
    "name": "SetOnceLine",
    "label": "Line",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "item", "label": "Item", "fieldtype": "Data"},
        {"fieldname": "serial", "label": "Serial", "fieldtype": "Data", "no_copy": True},
    ],
}

DOCTYPE = {
    "name": "SetOnceDoc",
    "label": "Registered letter",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {
            "fieldname": "reg_number",
            "label": "Reg. number",
            "fieldtype": "Data",
            "no_copy": True,
            "set_only_once": True,
        },
        {"fieldname": "lines", "label": "Lines", "fieldtype": "Table", "options": "SetOnceLine"},
    ],
    "permissions": [{"role": "Clerk", "actions": ["read", "write", "create"]}],
}

CLERK = make_user("clerk@grunt.example.com", roles=["Clerk"])


@pytest.fixture
async def doctypes(ctx):
    await save_doctype(doctype_data={**LINE, "__is_new": True})
    await save_doctype(doctype_data={**DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


async def _letter(db_session, engine, **values) -> dict:
    async with grunt.context(db_session, engine, CLERK):
        doc = await grunt.new_doc("SetOnceDoc", {"title": "Letter", **values})
    return doc


@pytest.mark.asyncio
async def test_set_only_once_holds_after_the_first_value(ctx, doctypes, db_session, engine):
    doc = await _letter(db_session, engine)
    await ctx.db._session().commit()
    async with grunt.context(db_session, engine, CLERK):
        # Empty so far - the first value may be set, other fields stay editable.
        await grunt.save_doc("SetOnceDoc", doc["name"], {"reg_number": "ВХ-1"})
        await grunt.save_doc("SetOnceDoc", doc["name"], {"title": "Renamed", "reg_number": "ВХ-1"})
        with pytest.raises(HTTPException) as save_error:
            await grunt.save_doc("SetOnceDoc", doc["name"], {"reg_number": "ВХ-2"})
        with pytest.raises(HTTPException) as set_error:
            await grunt.set_value("SetOnceDoc", doc["name"], "reg_number", "ВХ-3")
    assert save_error.value.status_code == 403
    assert set_error.value.status_code == 403
    assert await ctx.db.get_value("SetOnceDoc", doc["name"], "reg_number") == "ВХ-1"


@pytest.mark.asyncio
async def test_the_system_user_may_change_a_set_once_field(ctx, doctypes, db_session, engine):
    doc = await _letter(db_session, engine, reg_number="ВХ-1")
    await ctx.db._session().commit()
    # ctx acts as the internal system user (imports, fixtures, migrations).
    await ctx.save_doc("SetOnceDoc", doc["name"], {"reg_number": "ВХ-9"})
    assert await ctx.db.get_value("SetOnceDoc", doc["name"], "reg_number") == "ВХ-9"


@pytest.mark.asyncio
async def test_no_copy_fields_stay_out_of_a_duplicate(ctx, doctypes, db_session, engine):
    from grunt.api.v1.document.meta import get_copy

    doc = await _letter(
        db_session,
        engine,
        reg_number="ВХ-1",
        lines=[{"item": "Laptop", "serial": "SN-1"}],
    )
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, CLERK):
        data = await get_copy("SetOnceDoc", doc["name"])
        copy = await grunt.copy_doc("SetOnceDoc", doc["name"])

    for values in (data, copy):
        assert values["title"] == "Letter"
        assert not values.get("reg_number")
        assert [r["item"] for r in values["lines"]] == ["Laptop"]
        assert not values["lines"][0].get("serial")
    # Standard columns are the copy's own.
    assert not {"name", "owner", "created_at", "modified_at", "modified_by"} & set(data)
    assert copy["name"] != doc["name"]
