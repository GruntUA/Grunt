"""Renaming / touching one's own passkey - the role grants no ``write`` on
WebAuthnCredential (credentials change only through these endpoints), so the
endpoints check ownership themselves and write past the role rules."""

import pytest

from tests.support import make_user


@pytest.mark.asyncio
async def test_rename_and_touch_own_passkey(ctx, db_session, engine):
    from grunt.auth.doctypes.WebAuthnCredential.web_authn_credential import (
        rename_passkey,
        touch_passkey,
    )
    from grunt.errors import ApplicationError

    for email in ("pk-owner@x.com", "pk-other@x.com"):
        await ctx.new_doc("User", {"email": email, "first_name": "P", "last_name": "K"})
    cred = await ctx.new_doc(
        "WebAuthnCredential",
        {"user": "pk-owner@x.com", "label": "Old", "credential_id": "c1", "public_key": "k"},
    )
    await ctx.db._session().commit()

    owner = make_user("pk-owner@x.com")
    owner.data["name"] = "pk-owner@x.com"
    async with ctx.context(db_session, engine, owner):
        assert await rename_passkey(name=cred["name"], label="Laptop")
        assert await touch_passkey(name=cred["name"])
    assert await ctx.db.get_value("WebAuthnCredential", cred["name"], "label") == "Laptop"
    assert await ctx.db.get_value("WebAuthnCredential", cred["name"], "last_used_at")

    other = make_user("pk-other@x.com")
    other.data["name"] = "pk-other@x.com"
    async with ctx.context(db_session, engine, other):
        with pytest.raises(ApplicationError):  # not found - not theirs
            await rename_passkey(name=cred["name"], label="Mine now")
    assert await ctx.db.get_value("WebAuthnCredential", cred["name"], "label") == "Laptop"
