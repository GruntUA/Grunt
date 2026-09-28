"""SystemSettings.session_timeout is the idle timeout of a UserSession."""

from __future__ import annotations

from datetime import UTC, datetime

import jwt
import pytest

from grunt.config import settings as cfg
from grunt.site.settings import clear_settings_cache


async def _set_timeout(ctx, minutes: int | None) -> None:
    await ctx.db.set_value("SystemSettings", "SystemSettings", {"session_timeout": minutes})
    await ctx.db._session().commit()
    clear_settings_cache()


@pytest.mark.asyncio
async def test_access_token_is_short_and_capped_by_timeout(ctx):
    from grunt.auth.doctypes.User.user import create_user
    from grunt.auth.service import (
        ACCESS_TOKEN_MAX_MINUTES,
        access_token_minutes,
        create_access_token,
        session_ttl_minutes,
    )

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        user = await create_user("ttl@grunt.example.com", "correct-horse", "T", "L", None)
        await ctx.db._session().commit()

        await _set_timeout(ctx, 480)
        assert await session_ttl_minutes() == 480
        assert await access_token_minutes() == ACCESS_TOKEN_MAX_MINUTES

        await _set_timeout(ctx, 5)
        assert await access_token_minutes() == 5

        token = create_access_token(user, await access_token_minutes(), sid="abc")
        payload = jwt.decode(token, cfg.secret_key, algorithms=[cfg.algorithm])
        remaining = payload["exp"] - datetime.now(UTC).timestamp()
        assert 4 * 60 < remaining <= 5 * 60 + 5
        assert payload["sid"] == "abc"


@pytest.mark.asyncio
async def test_session_ttl_falls_back_when_unset(ctx):
    from grunt.auth.service import session_ttl_minutes

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await _set_timeout(ctx, None)
        assert await session_ttl_minutes() == cfg.access_token_expire_minutes
