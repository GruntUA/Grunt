"""Retention-based cleanup for is_log DocTypes (ErrorLog, ActivityLog, etc.).

Every DocType flagged ``is_log: true`` accumulates rows forever unless
something purges old ones. Retention is
per-DocType (``log_retention_days`` in its JSON), falling back to the
site-wide ``SystemSettings.log_retention_days``, and finally to
DEFAULT_LOG_RETENTION_DAYS when neither is set.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from grunt.app import grunt
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task

DEFAULT_LOG_RETENTION_DAYS = 30


@retryable_task()
async def purge_old_logs() -> None:
    """Delete rows older than retention for every is_log DocType."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    now = datetime.now(UTC)

    async with maker() as session, grunt.system_context(session, eng):
        from grunt.site.settings import get_setting

        default_retention = await get_setting("log_retention_days", DEFAULT_LOG_RETENTION_DAYS)

        doctypes = await doctype_registry.list_all()
        log_doctypes = [dt for dt in doctypes if dt.is_log and not dt.is_virtual]

        total_deleted = 0
        for dt in log_doctypes:
            retention_days = dt.log_retention_days or default_retention
            cutoff = now - timedelta(days=retention_days)
            try:
                deleted = await grunt.db.delete(dt.name, {"created_at__lt": cutoff})
                if deleted:
                    log.info(
                        "log_cleanup.purged",
                        doctype=dt.name,
                        deleted=deleted,
                        retention_days=retention_days,
                    )
                total_deleted += deleted
            except Exception as e:
                log.warning("log_cleanup.purge_failed", doctype=dt.name, error=str(e))

        await session.commit()
        log.info(
            "log_cleanup.done", doctypes_checked=len(log_doctypes), total_deleted=total_deleted
        )
