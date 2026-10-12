"""Cloud storage tasks - run by the task worker.

Every task binds the site's session and keeps no transaction open across
the network transfers (see grunt.backups.tasks._end_transaction: a worker's
SQLite transaction holds the write lock from its first statement).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import grunt
from grunt import _
from grunt.i18n import language_of, use_language
from grunt.progress import track_progress
from grunt.site.manager import site_manager
from grunt.storage.cloud import RemoteError, files_remote, load_remote, record_status
from grunt.tasks.broker import task

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@contextlib.asynccontextmanager
async def _site() -> AsyncIterator[str]:
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
        yield site


@contextlib.asynccontextmanager
async def _tracked(title: str, user: str | None, lang: str | None):
    with use_language(lang):
        async with track_progress(
            title, user=user, unit="bytes", doctype="StorageRemote", cancellable=True
        ) as progress:
            yield progress


@task
async def upload_latest_backup(name: str, user: str | None = None) -> str | None:
    """Upload the newest local backup set to the remote *name* (form button)."""
    from grunt.backups import list_backups
    from grunt.storage.cloud.backups import upload_backup

    async with _site() as site:
        remote = await load_remote(name)
        lang = await language_of(user)
        await grunt.get_session().commit()
        backups = list_backups(site)
        if not backups:
            return None
        async with _tracked(_("Upload to cloud storage"), user, lang) as progress:
            progress.set(total=backups[0].size())
            try:
                await upload_backup(site, backups[0], remote, progress)
            except RemoteError as exc:
                await record_status(remote, exc)
                raise
        await record_status(
            remote, None, last_backup_at=datetime.now(UTC), last_backup_id=backups[0].id
        )
        return backups[0].id


@task
async def fetch_backup(name: str, backup_id: str, user: str | None = None) -> str:
    """Download the set *backup_id* from the remote *name* into ``backups/``."""
    from grunt.storage.cloud.backups import fetch_backup as fetch

    async with _site() as site:
        remote = await load_remote(name)
        lang = await language_of(user)
        await grunt.get_session().commit()
        async with _tracked(_("Download from cloud storage"), user, lang) as progress:
            await fetch(site, remote, backup_id, progress)
        return backup_id


async def _offload(remote: dict[str, Any], progress=None) -> dict[str, int]:
    from grunt.storage.cloud.files import offload

    try:
        report = await offload(remote, progress)
    except RemoteError as exc:
        await record_status(remote, exc)
        raise
    await record_status(remote, None)
    return report


@task
async def offload_files() -> dict[str, int] | None:
    """Nightly: move old files into the files remote, if one is set up."""
    async with _site():
        remote = await files_remote()
        await grunt.get_session().commit()
        if remote is None:
            return None
        return await _offload(remote)


@task
async def offload_now(name: str, user: str | None = None) -> dict[str, int]:
    async with _site():
        remote = await load_remote(name)
        lang = await language_of(user)
        await grunt.get_session().commit()
        async with _tracked(_("Moving files to cloud storage"), user, lang) as progress:
            return await _offload(remote, progress)


@task
async def recall_files(name: str, user: str | None = None) -> dict[str, int]:
    from grunt.storage.cloud.files import recall

    async with _site():
        remote = await load_remote(name)
        lang = await language_of(user)
        await grunt.get_session().commit()
        async with _tracked(_("Returning files from cloud storage"), user, lang) as progress:
            try:
                return await recall(remote, progress)
            except RemoteError as exc:
                await record_status(remote, exc)
                raise
