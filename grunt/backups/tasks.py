"""Backup tasks — run by the task worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import grunt
from grunt import _, log, log_error
from grunt.backups import DEFAULT_COMPRESSION_LEVEL, create_backup, list_backups, rotate
from grunt.i18n import language_of, use_language
from grunt.progress import TaskCancelledError, track_progress
from grunt.site.manager import site_manager
from grunt.tasks.broker import task

# A backup counts as due a little early, so a job that fires on the hour
# doesn't skip a whole interval because the previous run took a minute.
_DUE_SLACK = timedelta(minutes=10)


async def _settings() -> dict:
    from grunt.site.settings import get_setting

    return {
        "enabled": bool(await get_setting("backup_enabled", True)),
        "interval": int(await get_setting("backup_interval_hours", 24) or 24),
        "keep": int(await get_setting("backup_keep", 7) or 7),
        "with_files": bool(await get_setting("backup_include_files", True)),
        "level": int(
            await get_setting("backup_compression_level", DEFAULT_COMPRESSION_LEVEL)
            or DEFAULT_COMPRESSION_LEVEL
        ),
    }


async def _end_transaction(session) -> None:
    """Close the settings read before the minutes of disk I/O.

    The worker opens every SQLite transaction with ``BEGIN IMMEDIATE``
    (grunt/db/write_intent.py): left open, it would hold the database write
    lock for the whole backup and every save on the site would time out.
    """
    await session.rollback()


def is_due(site: str, interval_hours: int, now: datetime | None = None) -> bool:
    backups = list_backups(site)
    if not backups:
        return True
    now = now or datetime.now(UTC)
    return now - backups[0].created_at >= timedelta(hours=interval_hours) - _DUE_SLACK


async def _run(site: str, *, keep: int, **options: Any) -> str:
    try:
        backup = await create_backup(site, **options)
    except TaskCancelledError:
        log.info("backup.cancelled", site=site)
        raise
    except Exception as exc:
        await log_error(exc=exc, title="Backup failed", context="Background Task")
        raise
    removed = rotate(site, keep)
    if removed:
        log.info("backup.rotated", site=site, removed=removed)
    return backup.id


@task
async def scheduled_backup() -> str | None:
    """Hourly: make a backup if the configured interval has passed."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
        cfg = await _settings()
        await _end_transaction(session)
        if not cfg["enabled"] or not is_due(site, cfg["interval"]):
            return None
        return await _run(site, keep=cfg["keep"], with_files=cfg["with_files"], level=cfg["level"])


@task
async def backup_now(
    with_database: bool = True,
    with_files: bool = True,
    with_config: bool = True,
    user: str | None = None,
) -> str:
    """Make a backup right away (the «Резервні копії» list button) of the chosen parts.

    *user* (who pressed the button) sees its progress in the task panel.
    """
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
        cfg = await _settings()
        lang = await language_of(user)
        await _end_transaction(session)
        with use_language(lang):
            async with track_progress(
                _("Backup"), user=user, unit="bytes", doctype="Backup", cancellable=True
            ) as progress:
                return await _run(
                    site,
                    keep=cfg["keep"],
                    with_database=with_database,
                    with_files=with_files,
                    with_config=with_config,
                    level=cfg["level"],
                    progress=progress,
                )
