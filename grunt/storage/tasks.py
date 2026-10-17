"""Storage tasks - run by the task worker."""

from __future__ import annotations

import grunt
from grunt import _, log
from grunt.i18n import language_of, use_language
from grunt.progress import track_progress
from grunt.site.manager import site_manager
from grunt.storage.gc import collect_garbage as collect
from grunt.tasks.broker import retryable_task, task


@retryable_task()
async def collect_garbage() -> None:
    """Nightly: drop blobs no File row needs any more (grunt.storage.gc)."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session, grunt.system_context(session, eng):
        await collect()


@task
async def compress_images(user: str | None = None) -> dict | None:
    """Compress images stored before compression was on (grunt.storage.images);
    *user* (who started it) follows it in the task panel and may cancel it."""
    from grunt.storage.images import compress_existing

    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session, grunt.system_context(session, eng):
        with use_language(await language_of(user)):
            async with track_progress(
                _("Compressing images"), user=user, doctype="File", cancellable=True
            ) as progress:
                report = await compress_existing(apply=True, progress=progress)
                log.info("storage.images_compressed", **report)
                return report
    return None  # cancelled
