"""Integration tests: UserPermission restricts what a non-privileged user
sees/touches - lists, counts, single-doc read/write, the Restrictions popup
payload, is_default form defaults, and strict mode."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

import grunt
from grunt.api.v1.meta import save_doctype
from grunt.permissions.user_permissions import get_active_restrictions
from grunt.site.settings import clear_settings_cache
from tests.support import make_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

POST_DOCTYPE = {
    "name": "UPTestPost",
    "label": "UP Test Post",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "team", "label": "Team", "fieldtype": "Link", "options": "Role"},
    ],
    "permissions": [
        {"role": "Employee", "read": True, "write": True, "create": True, "delete": True},
    ],
}


def _employee(email: str) -> User:
    return make_user(email, roles=["Employee"])


@pytest.fixture
async def setup(ctx):
    from grunt.permissions.user_permissions import invalidate_user_permission_cache

    await save_doctype(doctype_data={**POST_DOCTYPE, "__is_new": True})
    await ctx.new_doc("Role", {"role_name": "Red"})
    await ctx.new_doc("Role", {"role_name": "Blue"})
    red = (await ctx.new_doc("UPTestPost", {"title": "red post", "team": "Red"}))["name"]
    blue = (await ctx.new_doc("UPTestPost", {"title": "blue post", "team": "Blue"}))["name"]
    await ctx.new_doc(
        "UserPermission",
        {"for_user": "alice@example.com", "allow": "Role", "for_value": "Red"},
    )
    await ctx.db._session().commit()
    invalidate_user_permission_cache()
    return {"red": red, "blue": blue}


@pytest.mark.asyncio
async def test_list_and_count_are_restricted(ctx, setup, db_session, engine):
    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        rows = await grunt.get_list("UPTestPost")
        assert [r["name"] for r in rows] == [setup["red"]]
        assert rows.meta["total"] == 1
        assert await grunt.count("UPTestPost", respect_permissions=True) == 1
        assert await grunt.count("UPTestPost") == 2  # raw path unchanged


@pytest.mark.asyncio
async def test_unrestricted_user_sees_everything(ctx, setup, db_session, engine):
    async with grunt.context(db_session, engine, _employee("nobody@example.com")):
        rows = await grunt.get_list("UPTestPost")
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_single_doc_read_and_write_blocked(ctx, setup, db_session, engine):
    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        assert (await grunt.get_doc("UPTestPost", setup["red"]))["name"] == setup["red"]
        with pytest.raises(HTTPException) as exc:
            await grunt.get_doc("UPTestPost", setup["blue"])
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException):
            await grunt.save_doc("UPTestPost", setup["blue"], {"title": "hijack"})


@pytest.mark.asyncio
async def test_new_values_are_checked_on_create_and_update(ctx, setup, db_session, engine):
    """The stored row alone isn't enough: a restricted user may neither create
    a record outside their scope nor move one of theirs out of it."""
    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        with pytest.raises(HTTPException) as exc:
            await grunt.new_doc("UPTestPost", {"title": "sneaky", "team": "Blue"})
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await grunt.save_doc("UPTestPost", setup["red"], {"team": "Blue"})
        assert exc.value.status_code == 403

        created = await grunt.new_doc("UPTestPost", {"title": "mine", "team": "Red"})
        assert created["team"] == "Red"
        await grunt.save_doc("UPTestPost", setup["red"], {"title": "renamed"})


@pytest.mark.asyncio
async def test_system_manager_is_exempt(ctx, setup, db_session, engine):
    sm = make_user("sm@example.com", roles=["System Manager", "Employee"])
    async with grunt.context(db_session, engine, sm):
        rows = await grunt.get_list("UPTestPost")
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_restrictions_popup_payload(ctx, setup, db_session, engine):
    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        restrictions = await get_active_restrictions("UPTestPost")
    assert restrictions == [{"field": "Team", "fieldname": "team", "allow": "Role", "value": "Red"}]


@pytest.mark.asyncio
async def test_is_default_form_defaults(ctx, setup, db_session, engine):
    from grunt.permissions.user_permissions import (
        get_user_permission_defaults,
        invalidate_user_permission_cache,
    )

    await grunt.new_doc(
        "UserPermission",
        {
            "for_user": "carol@example.com",
            "allow": "Role",
            "for_value": "Blue",
            "is_default": True,
        },
    )
    await ctx.db._session().commit()
    invalidate_user_permission_cache()

    async with grunt.context(db_session, engine, _employee("carol@example.com")):
        assert await get_user_permission_defaults("UPTestPost") == {"team": "Blue"}


TREE_DOCTYPE = {
    "name": "UPTestUnit",
    "label": "UP Test Unit",
    "module": "core",
    "is_tree": True,
    "tree_parent_field": "parent_unit",
    "autoname": "field:title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {
            "fieldname": "parent_unit",
            "label": "Parent",
            "fieldtype": "Link",
            "options": "UPTestUnit",
        },
    ],
    "permissions": [{"role": "Employee", "read": True}],
}

TREE_ASSET_DOCTYPE = {
    "name": "UPTestUnitAsset",
    "label": "UP Test Unit Asset",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "unit", "label": "Unit", "fieldtype": "Link", "options": "UPTestUnit"},
    ],
    "permissions": [{"role": "Employee", "read": True}],
}


@pytest.mark.asyncio
async def test_tree_allow_authorises_whole_subtree(ctx, db_session, engine):
    """A UserPermission on a parent tree node also grants its descendants -
    an institution -> all its sub-units."""
    from grunt.permissions.user_permissions import invalidate_user_permission_cache

    await save_doctype(doctype_data={**TREE_DOCTYPE, "__is_new": True})
    await save_doctype(doctype_data={**TREE_ASSET_DOCTYPE, "__is_new": True})
    await ctx.new_doc("UPTestUnit", {"title": "HQ"})
    await ctx.new_doc("UPTestUnit", {"title": "HQ-IT", "parent_unit": "HQ"})
    await ctx.new_doc("UPTestUnit", {"title": "HQ-IT-Ops", "parent_unit": "HQ-IT"})
    await ctx.new_doc("UPTestUnit", {"title": "Other"})

    at_hq = (await ctx.new_doc("UPTestUnitAsset", {"title": "hq", "unit": "HQ"}))["name"]
    at_it = (await ctx.new_doc("UPTestUnitAsset", {"title": "it", "unit": "HQ-IT"}))["name"]
    at_ops = (await ctx.new_doc("UPTestUnitAsset", {"title": "ops", "unit": "HQ-IT-Ops"}))["name"]
    at_other = (await ctx.new_doc("UPTestUnitAsset", {"title": "other", "unit": "Other"}))["name"]
    await ctx.new_doc(
        "UserPermission",
        {"for_user": "alice@example.com", "allow": "UPTestUnit", "for_value": "HQ"},
    )
    await ctx.db._session().commit()
    invalidate_user_permission_cache()

    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        names = {r["name"] for r in await grunt.get_list("UPTestUnitAsset")}
        assert names == {at_hq, at_it, at_ops}
        assert (await grunt.get_doc("UPTestUnitAsset", at_ops))["name"] == at_ops
        with pytest.raises(HTTPException) as exc:
            await grunt.get_doc("UPTestUnitAsset", at_other)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_strict_mode_hides_docs_without_link(ctx, setup, db_session, engine):
    from grunt.permissions.user_permissions import invalidate_user_permission_cache

    # A post with no team link - visible by default, hidden under strict mode.
    orphan = (await ctx.new_doc("UPTestPost", {"title": "no team"}))["name"]
    await ctx.db._session().commit()
    invalidate_user_permission_cache()

    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        names = {r["name"] for r in await grunt.get_list("UPTestPost")}
        assert names == {setup["red"], orphan}

    await ctx.db.set_value(
        "SystemSettings", "SystemSettings", {"apply_strict_user_permissions": True}
    )
    await ctx.db._session().commit()

    clear_settings_cache()

    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        names = {r["name"] for r in await grunt.get_list("UPTestPost")}
        assert names == {setup["red"]}
