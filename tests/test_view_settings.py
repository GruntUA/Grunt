"""A user's list settings on the server (FRAPPE_GAP #6): per DocType and view,
each user sees only their own."""

import pytest

import grunt
from grunt.api.v1.view_settings import get_view_settings, save_view_settings
from tests.support import make_user

ANNA = make_user("anna@grunt.example.com", roles=["Employee"])
BOHDAN = make_user("bohdan@grunt.example.com", roles=["Employee"])


@pytest.mark.asyncio
async def test_settings_are_per_user_and_view(ctx, db_session, engine):
    async with grunt.context(db_session, engine, ANNA):
        await save_view_settings("User", "columns", ["full_name", "email"])
        await save_view_settings("User", "list", {"sortKey": "email", "sortOrder": "desc"})
        await save_view_settings("User", "columns", ["email"])  # replaces, no second row
    async with grunt.context(db_session, engine, BOHDAN):
        await save_view_settings("User", "columns", ["full_name"])
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, ANNA):
        mine = await get_view_settings("User")
    assert mine == {"columns": ["email"], "list": {"sortKey": "email", "sortOrder": "desc"}}
    async with grunt.context(db_session, engine, BOHDAN):
        assert await get_view_settings("User") == {"columns": ["full_name"]}
    rows = await ctx.db.get_all("UserViewSettings", filters={"owner": ANNA.email}, limit=None)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_none_resets_and_unknown_doctype_is_refused(ctx, db_session, engine):
    from fastapi import HTTPException

    async with grunt.context(db_session, engine, ANNA):
        await save_view_settings("*", "recent", [{"doctype": "User", "id": "x"}])
        await save_view_settings("*", "recent", None)
        assert await get_view_settings("*") == {}
        with pytest.raises(HTTPException) as excinfo:
            await save_view_settings("NoSuchDocType", "columns", [])
    assert excinfo.value.status_code == 404
