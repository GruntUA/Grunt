"""The SystemSettings cache is invalidated when the singleton is saved."""

from __future__ import annotations

import pytest

from grunt.site.settings import get_setting


@pytest.mark.asyncio
async def test_after_save_invalidates_cache(ctx):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        # prime the cache
        assert await get_setting("password_min_length") == 1

        # save through the normal document pipeline (fires SystemSettings.after_save)
        await ctx.save_doc("SystemSettings", "SystemSettings", {"password_min_length": 12})
        await ctx.db._session().commit()

        # cache must reflect the new value without an explicit clear
        assert await get_setting("password_min_length") == 12
