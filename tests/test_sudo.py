"""grunt.sudo (PERMISSIONS_PLAN step 7b): a user's request steps past their
rights only for a stated reason, recorded in the Access Log."""

import pytest

from tests.support import make_user

BOX = {
    "name": "SudoBox",
    "label": "Sudo Box",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [{"role": "System Manager", "actions": ["read", "write", "create", "delete"]}],
}


async def count_boxes_for_the_counter():
    import grunt

    async with grunt.sudo("public counter of boxes"):
        return await grunt.count("SudoBox")


@pytest.mark.asyncio
async def test_sudo_runs_as_system_and_is_recorded(ctx, db_session, engine):
    import grunt
    from grunt.api.v1.meta import save_doctype
    from grunt.errors import APIError

    await save_doctype(doctype_data={**BOX, "__is_new": True})
    await ctx.new_doc("SudoBox", {"title": "A"})
    await ctx.db._session().commit()

    clerk = make_user("clerk@example.com", roles=["Clerk"])
    async with grunt.context(db_session, engine, clerk):
        try:  # no rights of their own: nothing, or refused
            own = await grunt.count("SudoBox", respect_permissions=True)
        except APIError:
            own = 0
        assert own == 0
        assert await count_boxes_for_the_counter() == 1
        assert grunt.get_user().email == "clerk@example.com"  # back to the user
    await db_session.commit()

    [row] = await ctx.db.get_all(
        "AccessLog", filters={"action": "Elevated"}, fields=["owner", "reason"], limit=5
    )
    assert row["owner"] == "clerk@example.com"
    assert row["reason"].startswith("public counter of boxes")
    assert "count_boxes_for_the_counter" in row["reason"]


@pytest.mark.asyncio
async def test_sudo_needs_a_reason(ctx, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, make_user("x@example.com")):
        with pytest.raises(ValueError):
            async with grunt.sudo("  "):
                pass
