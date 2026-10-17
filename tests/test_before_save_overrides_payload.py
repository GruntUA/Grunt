"""A ``before_save`` that puts a field back to its stored value wins over the
request payload (EmailAccount / StorageRemote keep a masked secret that way).

The update used to write the payload value whenever the hook's result equalled
the stored one - a form saved with an empty SMTP password wiped it.
"""

import pytest


@pytest.mark.asyncio
async def test_hook_restored_value_is_what_gets_stored(ctx):
    await ctx.new_doc(
        "EmailAccount",
        {"email_address": "a@example.com", "smtp_password": "SK", "provider": "Other"},
    )
    name = (await ctx.db.get_all("EmailAccount", pluck="name"))[0]

    await ctx.save_doc("EmailAccount", name, {"smtp_password": "", "smtp_port": 25})

    row = await ctx.db.get_value("EmailAccount", name, ["smtp_password", "smtp_port"])
    assert row == ["SK", 25]
