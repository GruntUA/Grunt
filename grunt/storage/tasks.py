"""Storage tasks - run by the task worker."""

from __future__ import annotations

import grunt
from grunt.site.manager import site_manager
from grunt.storage.gc import collect_garbage as collect
from grunt.tasks.broker import retryable_task


@retryable_task()
async def collect_garbage() -> None:
    """Nightly: drop blobs no File row needs any more (grunt.storage.gc)."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session, grunt.system_context(session, eng):
        await collect()
