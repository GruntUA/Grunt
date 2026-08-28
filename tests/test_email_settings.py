"""queue_email honours SystemSettings.default_email_account + email_footer."""

from __future__ import annotations

import pytest

from grunt.email.service import email_service
from grunt.site.settings import clear_settings_cache


@pytest.mark.asyncio
async def test_queue_email_uses_configured_account_and_footer(ctx):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        # Two outgoing accounts — the *configured* one must win over "first".
        await ctx.new_doc(
            "EmailAccount", {"email_address": "first@example.com", "enable_outgoing": True}
        )
        chosen = await ctx.new_doc(
            "EmailAccount", {"email_address": "chosen@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        await ctx.db.set_value(
            "SystemSettings",
            "SystemSettings",
            {
                "default_email_account": chosen["name"],
                "email_footer": "<p>З повагою, команда</p>",
            },
        )
        await ctx.db._session().commit()
        clear_settings_cache()

        record_id = await email_service.queue_email(
            session=ctx.db._session(),
            to="user@example.com",
            subject="Тема",
            body="Тіло листа",
            html_body="<p>Вітаємо</p>",
        )
        assert record_id

        row = (
            await ctx.db.get_all(
                "EmailQueue",
                filters={"name": record_id},
                fields=["email_account", "content"],
                limit=1,
            )
        )[0]
        assert row["email_account"] == chosen["name"]
        assert "<p>Вітаємо</p>" in row["content"]
        assert "З повагою, команда" in row["content"]


@pytest.mark.asyncio
async def test_queue_email_falls_back_to_first_outgoing(ctx):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        acct = await ctx.new_doc(
            "EmailAccount", {"email_address": "only@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        # No default configured, empty footer → plain passthrough.
        await ctx.db.set_value(
            "SystemSettings",
            "SystemSettings",
            {"default_email_account": None, "email_footer": ""},
        )
        await ctx.db._session().commit()
        clear_settings_cache()

        record_id = await email_service.queue_email(
            session=ctx.db._session(),
            to="user@example.com",
            subject="Тема",
            body="Тіло",
        )
        row = (
            await ctx.db.get_all(
                "EmailQueue",
                filters={"name": record_id},
                fields=["email_account", "content"],
                limit=1,
            )
        )[0]
        assert row["email_account"] == acct["name"]
        assert row["content"] == "Тіло"
