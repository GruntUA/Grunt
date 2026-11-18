"""Saved list filters (FRAPPE_GAP #6): the owner's, or shared with roles or
everyone - others only apply them."""

import pytest
from fastapi import HTTPException

import grunt
from grunt.api.v1.saved_filters import delete_saved_filter, list_saved_filters, save_saved_filter
from tests.support import make_user

FILTERS = [{"fieldname": "enabled", "op": "=", "value": "1"}]
OWNER = make_user("owner@grunt.example.com", roles=["Clerk"])
CLERK = make_user("clerk2@grunt.example.com", roles=["Clerk"])
OTHER = make_user("other@grunt.example.com", roles=["Driver"])
NOBODY_READS = make_user("guestish@grunt.example.com", roles=["Cook"])

DOCTYPE = "FilteredThing"


@pytest.fixture(autouse=True)
async def doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            "name": DOCTYPE,
            "label": "Filtered thing",
            "module": "core",
            "__is_new": True,
            "fields": [{"fieldname": "enabled", "label": "Enabled", "fieldtype": "Check"}],
            "permissions": [
                {"role": "Clerk", "actions": ["read"]},
                {"role": "Driver", "actions": ["read"]},
            ],
        }
    )
    await ctx.db._session().commit()


async def _titles(db_session, engine, user) -> dict[str, bool]:
    async with grunt.context(db_session, engine, user):
        return {f["title"]: f["mine"] for f in await list_saved_filters(DOCTYPE)}


@pytest.mark.asyncio
async def test_sharing(ctx, db_session, engine):
    async with grunt.context(db_session, engine, OWNER):
        await save_saved_filter(DOCTYPE, "Mine", FILTERS)
        await save_saved_filter(DOCTYPE, "Clerks", FILTERS, "Roles", ["Clerk"])
        await save_saved_filter(DOCTYPE, "All", FILTERS, "Everyone")
        # The same title again replaces it - no second row.
        await save_saved_filter(DOCTYPE, "All", FILTERS + FILTERS, "Everyone")
    await ctx.db._session().commit()

    assert await _titles(db_session, engine, OWNER) == {"All": True, "Clerks": True, "Mine": True}
    assert await _titles(db_session, engine, CLERK) == {"All": False, "Clerks": False}
    assert await _titles(db_session, engine, OTHER) == {"All": False}
    assert len(await ctx.db.get_all("SavedFilter", filters={"title": "All"}, limit=None)) == 1


@pytest.mark.asyncio
async def test_only_the_owner_changes_or_deletes(ctx, db_session, engine):
    async with grunt.context(db_session, engine, OWNER):
        shared = await save_saved_filter(DOCTYPE, "All", FILTERS, "Everyone")
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, CLERK):
        with pytest.raises(HTTPException):
            await delete_saved_filter(shared["name"])
        with pytest.raises(HTTPException):
            await save_saved_filter(DOCTYPE, "All", FILTERS, "Nobody", name=shared["name"])
    async with grunt.context(db_session, engine, OWNER):
        await delete_saved_filter(shared["name"])
    await ctx.db._session().commit()
    assert await _titles(db_session, engine, CLERK) == {}


@pytest.mark.asyncio
async def test_no_read_access_no_filters(ctx, db_session, engine):
    async with grunt.context(db_session, engine, NOBODY_READS):
        with pytest.raises(HTTPException) as excinfo:
            await list_saved_filters(DOCTYPE)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_roles_sharing_needs_roles(ctx, db_session, engine):
    async with grunt.context(db_session, engine, OWNER):
        with pytest.raises(HTTPException) as excinfo:
            await save_saved_filter(DOCTYPE, "Clerks", FILTERS, "Roles", [])
    assert excinfo.value.status_code == 422
