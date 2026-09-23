"""Backup tasks — run by the task worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from grunt.app import grunt
from grunt.backups import create_backup, list_backups, rotate
from grunt.log import log
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
    }


def is_due(site: str, interval_hours: int, now: datetime | None = None) -> bool:
    backups = list_backups(site)
    if not backups:
        return True
    now = now or datetime.now(UTC)
    return now - backups[0].created_at >= timedelta(hours=interval_hours) - _DUE_SLACK


async def _run(site: str, *, with_files: bool, keep: int) -> str:
    try:
        backup = await create_backup(site, with_files=with_files)
    except Exception as exc:
        await grunt.log_error(
            exc=exc, title="Резервне копіювання не вдалося", context="Background Task"
        )
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
        if not cfg["enabled"] or not is_due(site, cfg["interval"]):
            return None
        return await _run(site, with_files=cfg["with_files"], keep=cfg["keep"])


@task
async def backup_now() -> str:
    """Make a backup right away (the «Резервні копії» list button)."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
        cfg = await _settings()
        return await _run(site, with_files=cfg["with_files"], keep=cfg["keep"])
