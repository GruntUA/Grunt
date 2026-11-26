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


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    """A bench with one app ``demo`` (module ``demo``)."""
    from grunt.site.manager import site_manager
    from grunt.testkit import write_app_manifest

    module = tmp_path / "apps" / "demo" / "demo"
    module.mkdir(parents=True)
    write_app_manifest(tmp_path / "apps" / "demo")
    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "get_all_installed_apps", lambda: {"demo"})
    return module / "records" / "saved_filter"


def _ship(records_dir, slug: str, **values) -> None:
    import json

    folder = records_dir / slug
    folder.mkdir(parents=True)
    record = {"doctype": "SavedFilter", "ref_doctype": DOCTYPE, "filters": FILTERS, **values}
    (folder / f"{slug}.json").write_text(json.dumps(record))


@pytest.mark.asyncio
async def test_an_app_ships_filters(ctx, demo_app, db_session, engine):
    from grunt.standard_records import apply_records

    if await ctx.db.exists("GruntInstalledApp", "demo") is None:
        await ctx.new_doc("GruntInstalledApp", {"name": "demo", "title": "Demo"})
    _ship(
        demo_app,
        "overdue",
        name="demo-overdue",
        title="Overdue",
        shared_with="Roles",
        roles=["Clerk"],
    )
    _ship(demo_app, "all", name="demo-all", title="All shipped", shared_with="Everyone")
    _ship(demo_app, "hidden", name="demo-hidden", title="Hidden", shared_with="Nobody")
    _ship(demo_app, "no-roles", name="demo-no-roles", title="No roles", shared_with="Roles")

    # The unshared one and the one without roles are refused (nobody would
    # see them); the rest go in.
    assert await apply_records("demo", db_session, engine) == 2
    await db_session.commit()

    async with grunt.context(db_session, engine, CLERK):
        shipped = {f["title"]: f for f in await list_saved_filters(DOCTYPE)}
    assert set(shipped) == {"Overdue", "All shipped"}
    assert shipped["Overdue"]["standard"] and shipped["Overdue"]["app"] == "demo"
    assert not shipped["Overdue"]["mine"]
    assert await _titles(db_session, engine, OTHER) == {"All shipped": False}

    # Nobody deletes the app's filter from the list.
    async with grunt.context(db_session, engine, CLERK):
        with pytest.raises(HTTPException):
            await delete_saved_filter("demo-overdue")


@pytest.mark.asyncio
async def test_own_filters_are_not_standard(ctx, db_session, engine):
    async with grunt.context(db_session, engine, OWNER):
        saved = await save_saved_filter(DOCTYPE, "Mine", FILTERS)
    assert (saved["standard"], saved["app"]) == (False, None)
