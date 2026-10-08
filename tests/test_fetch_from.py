"""Server-side ``fetch_from``: documents saved from code/API get fetched values.

The form fills ``fetch_from`` fields in the browser; the write pipeline must do
the same so documents created by sync jobs, hooks and imports carry them, and
controllers see them in ``validate``.
"""

import pytest

pytestmark = pytest.mark.asyncio


CITY_DT = {
    "name": "FfCity",
    "label": "Ff City",
    "module": "core",
    "autoname": "field:title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {"fieldname": "region", "label": "Region", "fieldtype": "Text"},
        {"fieldname": "code", "label": "Code", "fieldtype": "Text"},
    ],
}

CUSTOMER_DT = {
    "name": "FfCustomer",
    "label": "Ff Customer",
    "module": "core",
    "fields": [
        {"fieldname": "city", "label": "City", "fieldtype": "Link", "options": "FfCity"},
        {
            "fieldname": "region",
            "label": "Region",
            "fieldtype": "Text",
            "fetch_from": "city.region",
        },
        {"fieldname": "code", "label": "Code", "fieldtype": "Text", "fetch_from": "city.code"},
    ],
}


@pytest.fixture
async def ff_doctypes(ctx):
    from grunt.api.v1.meta import save_doctype

    for data in (CITY_DT, CUSTOMER_DT):
        await save_doctype(doctype_data={**data, "__is_new": True})
    await ctx.new_doc("FfCity", {"title": "Kyiv", "region": "Kyivska", "code": "KV"})
    await ctx.new_doc("FfCity", {"title": "Lviv", "region": "Lvivska", "code": "LV"})
    await ctx.db._session().commit()


async def test_insert_fetches_from_link(ctx, ff_doctypes):
    doc = await ctx.new_doc("FfCustomer", {"city": "Kyiv"})
    assert (doc["region"], doc["code"]) == ("Kyivska", "KV")


async def test_update_refetches_when_link_changes(ctx, ff_doctypes):
    doc = await ctx.new_doc("FfCustomer", {"city": "Kyiv"})
    updated = await ctx.save_doc("FfCustomer", doc["name"], {"city": "Lviv"})
    assert (updated["region"], updated["code"]) == ("Lvivska", "LV")


async def test_manual_value_kept_under_unchanged_link(ctx, ff_doctypes):
    doc = await ctx.new_doc("FfCustomer", {"city": "Kyiv"})
    updated = await ctx.save_doc("FfCustomer", doc["name"], {"region": "Custom"})
    assert (updated["region"], updated["code"]) == ("Custom", "KV")


async def test_empty_or_missing_link_leaves_fields(ctx, ff_doctypes):
    doc = await ctx.new_doc("FfCustomer", {"region": "Manual"})
    assert (doc["region"], doc.get("code")) == ("Manual", None)
    missing = await ctx.new_doc("FfCustomer", {"city": "Nowhere", "region": "Manual"})
    assert missing["region"] == "Manual"
