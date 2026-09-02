"""Integration tests: single-hop ``link_field.target_field`` in DocPermission.match.

A permission rule ``match: "holder.login == user"`` on *Gear* means a user may
see a Gear row when the *Holder* it links to has ``login`` equal to the current
user — without denormalising the login onto Gear itself. Exercised through the
real read pipeline (``grunt.get_list`` / ``grunt.get_doc``), the row-level SQL
filter and the per-document check both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from tests.support import make_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

HOLDER_DOCTYPE = {
    "name": "PermTestHolder",
    "label": "Perm Test Holder",
    "module": "core",
    "fields": [
        {"fieldname": "login", "label": "Login", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "Employee", "read": True},
    ],
}

GEAR_DOCTYPE = {
    "name": "PermTestGear",
    "label": "Perm Test Gear",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {
            "fieldname": "holder",
            "label": "Holder",
            "fieldtype": "Link",
            "options": "PermTestHolder",
        },
    ],
    "permissions": [
        {"role": "Employee", "read": True, "match": "holder.login == user"},
    ],
}


@pytest.fixture
async def setup_doctypes(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**HOLDER_DOCTYPE, "__is_new": True})
    await save_doctype(doctype_data={**GEAR_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


def _employee(email: str) -> User:
    return make_user(email, roles=["Employee"])


@pytest.fixture
async def gear(ctx, setup_doctypes):
    alice_h = (await ctx.new_doc("PermTestHolder", {"login": "alice@example.com"}))["name"]
    bob_h = (await ctx.new_doc("PermTestHolder", {"login": "bob@example.com"}))["name"]
    alice_g = (
        await ctx.new_doc("PermTestGear", {"title": "Alice's laptop", "holder": alice_h})
    )["name"]
    bob_g = (
        await ctx.new_doc("PermTestGear", {"title": "Bob's laptop", "holder": bob_h})
    )["name"]
    orphan_g = (await ctx.new_doc("PermTestGear", {"title": "Unassigned"}))["name"]
    await ctx.db._session().commit()
    return {"alice_g": alice_g, "bob_g": bob_g, "orphan_g": orphan_g}


@pytest.mark.asyncio
async def test_get_list_filters_via_linked_field(ctx, gear, db_session, engine):
    from grunt.app import grunt

    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        result = await grunt.get_list("PermTestGear")

    names = {row["name"] for row in result}
    assert names == {gear["alice_g"]}
    assert result.meta["total"] == 1


@pytest.mark.asyncio
async def test_get_doc_allows_own_denies_others(ctx, gear, db_session, engine):
    from grunt.app import grunt

    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        own = await grunt.get_doc("PermTestGear", gear["alice_g"])
        assert own["name"] == gear["alice_g"]

        with pytest.raises(HTTPException) as exc_info:
            await grunt.get_doc("PermTestGear", gear["bob_g"])
        assert exc_info.value.status_code == 403

        # Link unset → "holder.login == user" cannot hold → denied.
        with pytest.raises(HTTPException) as exc_info:
            await grunt.get_doc("PermTestGear", gear["orphan_g"])
        assert exc_info.value.status_code == 403
