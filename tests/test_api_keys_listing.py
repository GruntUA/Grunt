"""Regression: list_api_keys() had dead code — `filters = {"user_id": user.id}`
was set unconditionally, then the `if not user.is_superadmin:` branch set the
exact same value again. Superadmins could never see anyone's keys but their
own, even though the comment ("Non-superadmins can only see their own keys")
implies they should see everyone's.
"""

from __future__ import annotations

import pytest

from tests.support import make_user


def _fake_user(email: str, name: str, *, is_superadmin: bool = False):
    # ApiKey.json restricts read/write to role "System Manager" — every test
    # user needs it just to reach list_api_keys() at all; is_superadmin then
    # additionally controls whether they see everyone's keys or only their own.
    user = make_user(email, roles=["System Manager"], is_superadmin=is_superadmin)
    user.data["name"] = name
    return user


@pytest.mark.asyncio
async def test_regular_user_sees_only_own_keys(ctx, db_session, engine):
    from grunt.auth.doctypes.ApiKey.api_key import list_api_keys
    from grunt.app import grunt

    alice = _fake_user("alice@grunt.example.com", "alice-id")
    bob = _fake_user("bob@grunt.example.com", "bob-id")

    async with ctx.system_context(ctx.db._session()):
        await ctx.new_doc(
            "ApiKey",
            {
                "label": "Alice's key",
                "user_id": alice.id,
                "key_prefix": "aaaaaaaa",
                "key_hash": "hash-a",
                "is_active": True,
            },
        )
        await ctx.new_doc(
            "ApiKey",
            {
                "label": "Bob's key",
                "user_id": bob.id,
                "key_prefix": "bbbbbbbb",
                "key_hash": "hash-b",
                "is_active": True,
            },
        )
        await ctx.db._session().commit()

    async with grunt.context(db_session, engine, alice):
        result = await list_api_keys(user=alice)
    labels = {k["label"] for k in result}
    assert labels == {"Alice's key"}


@pytest.mark.asyncio
async def test_superadmin_sees_all_keys(ctx, db_session, engine):
    from grunt.auth.doctypes.ApiKey.api_key import list_api_keys
    from grunt.app import grunt

    alice = _fake_user("alice2@grunt.example.com", "alice2-id")
    bob = _fake_user("bob2@grunt.example.com", "bob2-id")
    admin = _fake_user("admin@grunt.example.com", "admin-id", is_superadmin=True)

    async with ctx.system_context(ctx.db._session()):
        await ctx.new_doc(
            "ApiKey",
            {
                "label": "Alice2's key",
                "user_id": alice.id,
                "key_prefix": "cccccccc",
                "key_hash": "hash-c",
                "is_active": True,
            },
        )
        await ctx.new_doc(
            "ApiKey",
            {
                "label": "Bob2's key",
                "user_id": bob.id,
                "key_prefix": "dddddddd",
                "key_hash": "hash-d",
                "is_active": True,
            },
        )
        await ctx.db._session().commit()

    async with grunt.context(db_session, engine, admin):
        result = await list_api_keys(user=admin)
    labels = {k["label"] for k in result}
    assert {"Alice2's key", "Bob2's key"} <= labels
