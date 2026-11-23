"""An API key never gets more than its user (PERMISSIONS_PLAN step 7a): it may
act with only some of the user's roles, and a read-only key only reads."""

import pytest

from grunt.auth.api_key_service import authenticate_api_key, generate_api_key


async def _user(ctx, email: str, *roles: str) -> str:
    for role in roles:
        if not await ctx.db.exists("Role", {"role_name": role}):
            await ctx.new_doc("Role", {"role_name": role})
    doc = await ctx.new_doc(
        "User",
        {
            "email": email,
            "first_name": "K",
            "last_name": "Ey",
            "roles": [{"role_name": r} for r in roles],
        },
    )
    return doc["name"]


async def _key(ctx, user_id: str, **extra) -> str:
    full_key, prefix, key_hash = generate_api_key()
    await ctx.new_doc(
        "ApiKey",
        {
            "label": "k",
            "user_id": user_id,
            "key_prefix": prefix,
            "key_hash": key_hash,
            "is_active": True,
            **extra,
        },
    )
    await ctx.db._session().commit()
    return full_key


@pytest.mark.asyncio
async def test_key_acts_with_its_roles_only(ctx, db_session):
    user = await _user(ctx, "keyuser@example.com", "KeyClerk", "KeyAuditor")
    key = await _key(ctx, user, roles=[{"role_name": "KeyAuditor"}])
    found = await authenticate_api_key(key, db_session)
    assert found is not None
    assert found.roles == ["KeyAuditor"]
    assert [r["role_name"] for r in found.role_rows] == ["KeyAuditor"]

    # Without roles on the key - all of the user's.
    plain = await _key(ctx, user)
    assert sorted((await authenticate_api_key(plain, db_session)).data["roles"]) == [
        "KeyAuditor",
        "KeyClerk",
    ]


@pytest.mark.asyncio
async def test_key_cannot_get_a_role_its_user_lacks(ctx):
    from grunt.errors import APIError

    user = await _user(ctx, "keyuser2@example.com", "KeyClerk")
    await ctx.new_doc("Role", {"role_name": "KeyOther"})
    with pytest.raises(APIError):
        await _key(ctx, user, roles=[{"role_name": "KeyOther"}])


@pytest.mark.asyncio
async def test_read_only_key_reads_and_nothing_else(ctx, client, auth_headers):
    resp = await client.post(
        "/api/v1/method/grunt.auth.doctypes.ApiKey.api_key.create_api_key",
        json={"label": "reader", "read_only": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    headers = {"X-Api-Key": resp.json()["data"]["key"]}

    assert (await client.get("/api/v1/docs/Role", headers=headers)).status_code == 200
    resp = await client.post("/api/v1/docs/Role", json={"role_name": "ByKey"}, headers=headers)
    assert resp.status_code == 403
    assert not await ctx.db.exists("Role", {"role_name": "ByKey"})


@pytest.mark.asyncio
async def test_read_only_key_cannot_write_even_through_a_get(ctx, db_session, engine):
    """A method reached by GET that writes is refused by the permission check."""
    import grunt
    from grunt.local import READ_ONLY_KEY
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.rbac import permission_checker
    from tests.support import make_user

    reader = make_user("ro@example.com", is_superadmin=True)
    reader.data[READ_ONLY_KEY] = True
    meta = await doctype_registry.get_meta("Role")
    async with grunt.context(db_session, engine, reader):
        assert await permission_checker.check(meta, "read")
        assert not await permission_checker.check(meta, "write")
        assert not await permission_checker.check(meta, "create")
