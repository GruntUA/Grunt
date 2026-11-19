"""Apps and sidebar items show only what the user may open: ``AppMenu.roles``,
read on the item's DocType (a role or a share), an app with nothing left is
hidden; a desk manager sees everything."""

import pytest
from fastapi import HTTPException

from tests.support import make_user

BOB = "bob@example.com"


def _doctype(name: str, roles: list[str]) -> dict:
    return {
        "name": name,
        "label": name,
        "module": "core",
        "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
        "permissions": [
            {"role": "System Manager", "actions": ["read", "write", "create", "delete", "share"]},
            *({"role": r, "actions": ["read"]} for r in roles),
        ],
    }


def _item(link_to: str, section: str = "Main", **extra: object) -> dict:
    return {"type": "DocType", "label": link_to, "link_to": link_to, "section": section, **extra}


def _divider(section: str = "Main") -> dict:
    return {"type": "Divider", "label": "", "section": section}


@pytest.fixture
async def menus(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_doctype("OpenBox", ["Clerk"]), "__is_new": True})
    await save_doctype(doctype_data={**_doctype("ClosedBox", []), "__is_new": True})
    await save_doctype(doctype_data={**_doctype("SharedBox", []), "__is_new": True})
    await ctx.new_doc("User", {"email": BOB, "first_name": "Bob", "last_name": "Ser"})
    await ctx.new_doc(
        "AppMenu",
        {
            "name": "office",
            "label": "Office",
            "sidebar_items": [
                _divider(),
                _item("OpenBox", show_count=1),
                _divider(),
                _item("ClosedBox", show_count=1),
                _divider(),
                _item("SharedBox"),
                _item("ClosedBox", section="Admin"),
                {"type": "URL", "label": "Site", "link_to": "/", "section": "Links"},
            ],
        },
    )
    await ctx.new_doc(
        "AppMenu", {"name": "vault", "label": "Vault", "sidebar_items": [_item("ClosedBox")]}
    )
    await ctx.new_doc(
        "AppMenu",
        {"name": "bosses", "label": "Bosses", "roles": "Boss", "sidebar_items": [_item("OpenBox")]},
    )
    await ctx.db._session().commit()


def _bob(*roles: str):
    return make_user(BOB, roles=list(roles))


async def _as(db_session, engine, user, fn, *args):
    import grunt

    async with grunt.context(db_session, engine, user):
        return await fn(*args)


@pytest.mark.asyncio
async def test_only_readable_items_and_apps(ctx, menus, db_session, engine):
    from grunt.api.v1.workspace import list_workspaces

    apps = await _as(db_session, engine, _bob("Clerk"), list_workspaces)
    by_name = {a["name"]: a for a in apps}
    # Vault has nothing Bob may open; Bosses is for another role.
    assert "vault" not in by_name
    assert "bosses" not in by_name
    office = by_name["office"]
    assert [(i["type"], i["label"]) for i in office["items"]] == [
        ("DocType", "OpenBox"),
        ("URL", "Site"),
    ]
    assert [s["section"] for s in office["sections"]] == ["Main", "Links"]


@pytest.mark.asyncio
async def test_app_roles_let_the_role_in(ctx, menus, db_session, engine):
    from grunt.api.v1.workspace import list_workspaces

    apps = await _as(db_session, engine, _bob("Clerk", "Boss"), list_workspaces)
    assert "bosses" in {a["name"] for a in apps}


@pytest.mark.asyncio
async def test_a_share_makes_the_item_visible(ctx, menus, db_session, engine):
    from grunt.api.v1.workspace import list_workspaces

    doc = await ctx.new_doc("SharedBox", {"title": "One"})
    await ctx.new_doc(
        "SharedWith",
        {"reference_doctype": "SharedBox", "reference_id": doc["name"], "user": BOB},
    )
    await ctx.db._session().commit()

    apps = await _as(db_session, engine, _bob("Clerk"), list_workspaces)
    office = next(a for a in apps if a["name"] == "office")
    assert [i["label"] for i in office["items"] if i["type"] != "Divider"] == [
        "OpenBox",
        "SharedBox",
        "Site",
    ]
    # A divider between two visible items of its section stays.
    assert [i["type"] for i in office["items"]][:3] == ["DocType", "Divider", "DocType"]


@pytest.mark.asyncio
async def test_manager_sees_everything(ctx, menus, db_session, engine):
    from grunt.api.v1.workspace import list_workspaces

    apps = await _as(db_session, engine, make_user(BOB, roles=["System Manager"]), list_workspaces)
    by_name = {a["name"]: a for a in apps}
    assert {"office", "vault", "bosses"} <= set(by_name)
    assert len(by_name["office"]["items"]) == 8


@pytest.mark.asyncio
async def test_closed_app_is_forbidden(ctx, menus, db_session, engine):
    from grunt.api.v1.workspace import get_workspace

    with pytest.raises(HTTPException) as exc:
        await _as(db_session, engine, _bob("Clerk"), get_workspace, "vault")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        await _as(db_session, engine, _bob("Clerk"), get_workspace, "bosses")
    office = await _as(db_session, engine, _bob("Clerk"), get_workspace, "office")
    assert office["name"] == "office"


@pytest.mark.asyncio
async def test_counts_only_for_visible_items(ctx, menus, db_session, engine):
    from grunt.api.v1.workspace import get_counts

    counts = await _as(db_session, engine, _bob("Clerk"), get_counts, "office")
    assert set(counts) == {"OpenBox"}
    assert await _as(db_session, engine, _bob("Clerk"), get_counts, "bosses") == {}


@pytest.mark.asyncio
async def test_allowed_doctypes_batches_shares(ctx, menus, db_session, engine):
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.query import allowed, allowed_doctypes

    doc = await ctx.new_doc("SharedBox", {"title": "One"})
    await ctx.new_doc(
        "SharedWith",
        {"reference_doctype": "SharedBox", "reference_id": doc["name"], "user": BOB},
    )
    await ctx.db._session().commit()
    metas = [await doctype_registry.get_meta(n) for n in ("OpenBox", "ClosedBox", "SharedBox")]

    async def check():
        batched = await allowed_doctypes(metas, "read")
        one_by_one = {m.name for m in metas if await allowed(m, "read")}
        return batched, one_by_one

    batched, one_by_one = await _as(db_session, engine, _bob("Clerk"), check)
    assert batched == one_by_one == {"OpenBox", "SharedBox"}


@pytest.mark.asyncio
async def test_page_items_by_publication_and_roles(ctx, menus, db_session, engine):
    from grunt.api.v1.workspace import get_workspace

    for name, published, roles in (
        ("open-page", 1, ""),
        ("draft-page", 0, ""),
        ("boss-page", 1, "Boss"),
    ):
        await ctx.new_doc(
            "Page", {"name": name, "label": name, "is_published": published, "roles": roles}
        )
    await ctx.new_doc(
        "AppMenu",
        {
            "name": "pages",
            "label": "Pages",
            "sidebar_items": [
                {"type": "Page", "label": n, "link_to": n, "section": "Main"}
                for n in ("open-page", "draft-page", "boss-page")
            ],
        },
    )
    await ctx.db._session().commit()

    menu = await _as(db_session, engine, _bob("Clerk"), get_workspace, "pages")
    assert [i["label"] for i in menu["items"]] == ["open-page"]
    menu = await _as(db_session, engine, _bob("Clerk", "Boss"), get_workspace, "pages")
    assert [i["label"] for i in menu["items"]] == ["open-page", "boss-page"]
