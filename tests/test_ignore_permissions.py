"""``documents.*(..., ignore_permissions=True)``: the call steps past every
permission check (as the system would), but what it writes keeps the name of
the user it runs for - ``owner`` / ``modified_by``; without a real user (a
Guest, the system itself) they stay the system's."""

import pytest
import pytest_asyncio
from fastapi import HTTPException

from grunt.auth.constants import GUEST_USER_EMAIL, SYSTEM_USER_EMAIL
from grunt.local import session_user
from tests.support import make_user

VAULT = {
    "name": "IpVault",
    "label": "Ip Vault",
    "module": "test",
    "autoname": "prompt",
    "fields": [{"fieldname": "note", "label": "Note", "fieldtype": "Data"}],
    "permissions": [{"role": "Keeper", "actions": ["read", "write", "create", "delete"]}],
}

NOBODY = make_user("nobody@x.com", roles=[])
GUEST = make_user(GUEST_USER_EMAIL, roles=["Guest"])


@pytest_asyncio.fixture
async def vault(ctx):
    from grunt.api.v1.meta import save_doctype, sync_doctype

    await save_doctype(doctype_data={**VAULT, "__is_new": True})
    await sync_doctype(name=VAULT["name"])


@pytest.mark.asyncio
async def test_without_the_flag_a_user_without_rights_is_refused(ctx, vault, db_session, engine):
    async with ctx.context(db_session, engine, NOBODY):
        with pytest.raises(HTTPException) as err:
            await ctx.new_doc("IpVault", {"name": "V0"})
    assert err.value.status_code == 403


@pytest.mark.asyncio
async def test_the_flag_passes_the_checks_but_stamps_the_user(ctx, vault, db_session, engine):
    async with ctx.context(db_session, engine, NOBODY):
        await ctx.new_doc("IpVault", {"name": "V1"}, ignore_permissions=True)
        assert session_user() == "nobody@x.com"  # the context is back
        await ctx.save_doc("IpVault", "V1", {"note": "changed"}, ignore_permissions=True)
        doc = await ctx.get_doc("IpVault", "V1", ignore_permissions=True)
        rows = await ctx.get_list("IpVault", fields=["name"], ignore_permissions=True)
        with pytest.raises(HTTPException):
            await ctx.get_doc("IpVault", "V1")
    assert doc["note"] == "changed"
    assert doc["owner"] == "nobody@x.com"
    assert doc["modified_by"] == "nobody@x.com"
    assert [r["name"] for r in rows] == ["V1"]


@pytest.mark.asyncio
async def test_without_a_real_user_the_system_owns_it(ctx, vault, db_session, engine):
    async with ctx.context(db_session, engine, GUEST):
        await ctx.new_doc("IpVault", {"name": "V2"}, ignore_permissions=True)
    async with ctx.system_context(db_session, engine):
        await ctx.new_doc("IpVault", {"name": "V3"}, ignore_permissions=True)
    owners = await ctx.db.get_all(
        "IpVault", filters={"name__in": ["V2", "V3"]}, pluck="owner", limit=None
    )
    assert set(owners) == {SYSTEM_USER_EMAIL}


@pytest.mark.asyncio
async def test_system_context_still_stamps_the_system(ctx, vault, db_session, engine):
    async with ctx.context(db_session, engine, NOBODY), ctx.system_context():
        await ctx.new_doc("IpVault", {"name": "V4"})
    assert await ctx.db.get_value("IpVault", "V4", "owner") == SYSTEM_USER_EMAIL
