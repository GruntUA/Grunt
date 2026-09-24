"""``__perms`` on a document: what the current user may do with it, computed by
the same checks the write paths enforce — roles, row-level match, shares."""

from __future__ import annotations

import pytest

from grunt.permissions.doc_perms import doc_permissions
from tests.support import make_user

BOX = {
    "name": "PermBox",
    "label": "Perm Box",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Reader", "read": True},
        {"role": "Author", "read": True, "write": True, "create": True, "match": "owner == user"},
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
    from grunt.app import grunt

    async with grunt.context(db_session, engine, user):
        doc = await grunt.get_doc("PermBox", name)
        return await doc_permissions("PermBox", doc)


@pytest.mark.asyncio
async def test_reader_can_only_read(box, db_session, engine):
    perms = await _perms_as(make_user(BOB, roles=["Reader"]), box, db_session, engine)
    assert perms == {"write": False, "delete": False, "create": False}


@pytest.mark.asyncio
async def test_row_level_match_decides_per_document(box, db_session, engine, ctx):
    # Author may write only what they own — this one was made by the system user.
    perms = await _perms_as(make_user(BOB, roles=["Author", "Reader"]), box, db_session, engine)
    assert perms == {"write": False, "delete": False, "create": True}


@pytest.mark.asyncio
async def test_write_share_grants_write_but_not_delete(box, db_session, engine, ctx):
    await ctx.new_doc(
        "SharedWith",
        {"reference_doctype": "PermBox", "reference_id": box, "user": BOB, "permission": "Write"},
    )
    await ctx.db._session().commit()
    perms = await _perms_as(make_user(BOB, roles=[]), box, db_session, engine)
    assert perms == {"write": True, "delete": False, "create": False}


@pytest.mark.asyncio
async def test_api_returns_perms_and_ignores_them_on_save(client, auth_headers):
    url = "/api/v1/docs/Role"
    r = await client.post(url, json={"role_name": "Perm Probe"}, headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    doc = r.json()["data"]
    assert doc["__perms"] == {"write": True, "delete": True, "create": True}

    got = (await client.get(f"{url}/{doc['name']}", headers=auth_headers)).json()["data"]
    assert got["__perms"]["write"] is True

    # The form sends the whole document back, __perms included: it is dropped.
    r = await client.put(
        f"{url}/{doc['name']}", json={**got, "description": "x"}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["description"] == "x"
