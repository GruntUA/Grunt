"""``__perms`` on a document: what the current user may do with it, computed by
the same checks the write paths enforce — roles, row-level match, shares."""

import pytest

from grunt.permissions.doc_perms import doc_permissions
from tests.support import make_user

BOX = {
    "name": "PermBox",
    "label": "Perm Box",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete", "share"]},
        {"role": "Reader", "actions": ["read", "print"]},
        {
            "role": "Author",
            "actions": ["read", "write", "create", "share"],
            "match": "owner == user",
        },
    ],
}
BOB = "bob@example.com"


@pytest.fixture
async def box(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, "__is_new": True})
    await ctx.new_doc("User", {"email": BOB, "first_name": "B", "last_name": "Ob"})
    name = (await ctx.new_doc("PermBox", {"title": "A"}))["name"]
    await ctx.db._session().commit()
    return name


async def _perms_as(user, name, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, user):
        doc = await grunt.get_doc("PermBox", name)
        return await doc_permissions("PermBox", doc)


@pytest.mark.asyncio
async def test_reader_can_only_read(box, db_session, engine):
    perms = await _perms_as(make_user(BOB, roles=["Reader"]), box, db_session, engine)
    assert perms == {
        "write": False,
        "delete": False,
        "create": False,
        "print": True,
        "share": False,
        "readonly_fields": [],
    }


@pytest.mark.asyncio
async def test_row_level_match_decides_per_document(box, db_session, engine, ctx):
    # Author may write only what they own — this one was made by the system user.
    perms = await _perms_as(make_user(BOB, roles=["Author", "Reader"]), box, db_session, engine)
    # `share` comes with the same row condition - and needs write besides.
    assert perms == {
        "write": False,
        "delete": False,
        "create": True,
        "print": True,
        "share": False,
        "readonly_fields": [],
    }


@pytest.mark.asyncio
async def test_write_share_grants_write_but_not_delete(box, db_session, engine, ctx):
    await ctx.new_doc(
        "SharedWith",
        {"reference_doctype": "PermBox", "reference_id": box, "user": BOB, "permission": "Write"},
    )
    await ctx.db._session().commit()
    perms = await _perms_as(make_user(BOB, roles=[]), box, db_session, engine)
    # A share hands out read/write only - never print, or sharing further.
    assert perms == {
        "write": True,
        "delete": False,
        "create": False,
        "print": False,
        "share": False,
        "readonly_fields": [],
    }


@pytest.mark.asyncio
async def test_author_may_share_own_documents(box, db_session, engine):
    import grunt

    author = make_user(BOB, roles=["Author"])
    async with grunt.context(db_session, engine, author):
        own = (await grunt.new_doc("PermBox", {"title": "mine"}))["name"]
    perms = await _perms_as(author, own, db_session, engine)
    assert perms["share"] is True
    assert perms["print"] is False


@pytest.mark.asyncio
async def test_api_returns_perms_and_ignores_them_on_save(client, auth_headers):
    url = "/api/v1/docs/Role"
    r = await client.post(url, json={"role_name": "Perm Probe"}, headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    doc = r.json()["data"]
    assert doc["__perms"] == {
        "write": True,
        "delete": True,
        "create": True,
        "print": True,
        "share": True,
        "readonly_fields": [],
    }

    got = (await client.get(f"{url}/{doc['name']}", headers=auth_headers)).json()["data"]
    assert got["__perms"]["write"] is True

    # The form sends the whole document back, __perms included: it is dropped.
    r = await client.put(
        f"{url}/{doc['name']}", json={**got, "description": "x"}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["description"] == "x"
