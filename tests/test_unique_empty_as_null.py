"""A unique field stores an empty value as NULL: many records may leave it
blank or clear it, only filled values must differ."""

import pytest
from sqlalchemy import text

from grunt.metadata.field import DocField

_CHILD = {
    "name": "UqLine",
    "label": "Uq Line",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "item", "label": "Item", "fieldtype": "Data"},
        {"fieldname": "serial", "label": "Serial", "fieldtype": "Data", "unique": True},
    ],
}

_PARENT = {
    "name": "UqCard",
    "label": "Uq Card",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "unique": True},
        {"fieldname": "lines", "label": "Lines", "fieldtype": "Table", "options": "UqLine"},
    ],
}


def test_coerce_turns_empty_into_null_only_for_unique_fields():
    unique = DocField(fieldname="code", label="Code", fieldtype="Data", unique=True)
    plain = DocField(fieldname="title", label="Title", fieldtype="Data")
    assert unique.coerce("") is None
    assert unique.coerce("A-1") == "A-1"
    assert plain.coerce("") == ""


@pytest.fixture
async def card_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_CHILD, "__is_new": True})
    await save_doctype(doctype_data={**_PARENT, "__is_new": True})
    await ctx.db._session().commit()


async def _codes(ctx) -> list:
    rows = await ctx.db._session().execute(
        text("SELECT code FROM grunt_core_uq_card ORDER BY name")
    )
    return [r[0] for r in rows]


@pytest.mark.asyncio
async def test_blank_and_cleared_unique_values_do_not_collide(ctx, card_doctype):
    await ctx.new_doc("UqCard", {"title": "a", "code": ""})
    await ctx.new_doc("UqCard", {"title": "b", "code": ""})
    third = await ctx.new_doc("UqCard", {"title": "c", "code": "X-1"})
    await ctx.save_doc("UqCard", third["name"], {"code": ""})
    assert await _codes(ctx) == [None, None, None]


@pytest.mark.asyncio
async def test_child_rows_leave_an_absent_unique_field_null(ctx, card_doctype):
    await ctx.new_doc("UqCard", {"title": "a", "lines": [{"item": "x"}, {"item": "y"}]})
    await ctx.new_doc("UqCard", {"title": "b", "lines": [{"item": "z", "serial": ""}]})
    rows = await ctx.db._session().execute(text("SELECT serial FROM grunt_core_uq_line"))
    assert [r[0] for r in rows] == [None, None, None]
