"""`list_api_keys()` restricts results to the caller's own keys unless they
are the owner of a queried key, or hold the "System Manager" role — which is
also the only role granted read access to ``ApiKey`` at all (see
``ApiKey.json``), so every caller in these tests needs it just to get any
result back. Since admin rights are granted purely through that role now
(no separate superadmin flag), any System Manager sees every user's keys —
there is no longer a further tier above it to distinguish.
"""

from __future__ import annotations

import pytest

from tests.support import make_user


def _fake_user(email: str, name: str):
    user = make_user(email, roles=["System Manager"])
    user.data["name"] = name
    return user


@pytest.mark.asyncio
async def test_system_manager_sees_all_keys(ctx, db_session, engine):
    import grunt
    from grunt.auth.doctypes.ApiKey.api_key import list_api_keys

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
    assert {"Alice's key", "Bob's key"} <= labels
