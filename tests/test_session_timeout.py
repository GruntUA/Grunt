"""SystemSettings.session_timeout drives access + refresh token TTL."""

from __future__ import annotations

from datetime import UTC, datetime

import jwt
import pytest

from grunt.config import settings as cfg
from grunt.site.settings import clear_settings_cache


@pytest.mark.asyncio
async def test_session_timeout_controls_token_ttl(ctx):
    from grunt.auth.doctypes.User.user import create_user
    from grunt.auth.service import (
        create_access_token,
        create_refresh_token,
        session_ttl_minutes,
    )

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        user = await create_user("ttl@grunt.example.com", "correct-horse", "T", "L", None)
        await ctx.db._session().commit()

        await ctx.db.set_value("SystemSettings", "SystemSettings", {"session_timeout": 30})
        await ctx.db._session().commit()
        clear_settings_cache()

        assert await session_ttl_minutes() == 30

        ttl = 30
        token = create_access_token(user, ttl)
        payload = jwt.decode(token, cfg.secret_key, algorithms=[cfg.algorithm])
        access_remaining = payload["exp"] - datetime.now(UTC).timestamp()
        assert 29 * 60 < access_remaining <= 30 * 60 + 5

        await create_refresh_token(user.id, ttl)
        row = (
            await ctx.db.get_all(
                "User",
                filters={"name": user.id},
                fields=["refresh_token_expires_at"],
                limit=1,
            )
        )[0]
        expires_at = row["refresh_token_expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        refresh_remaining = (expires_at - datetime.now(UTC)).total_seconds()
        assert 29 * 60 < refresh_remaining <= 30 * 60 + 5


@pytest.mark.asyncio
async def test_session_ttl_falls_back_when_unset(ctx):
    from grunt.auth.service import session_ttl_minutes

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.db.set_value("SystemSettings", "SystemSettings", {"session_timeout": None})
        await ctx.db._session().commit()
        clear_settings_cache()

        assert await session_ttl_minutes() == cfg.access_token_expire_minutes
