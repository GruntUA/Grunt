"""Retention - nightly deletion of documents older than their DocType allows.

``DocType.retention_days`` (+ optional ``retention_date_field``, default
``created_at``) sets the limit:

* ``is_log`` DocTypes (ErrorLog, ActivityLog, …) always have one - their own,
  else ``SystemSettings.log_retention_days``, else DEFAULT_LOG_RETENTION_DAYS -
  and are purged with one bulk DELETE (no hooks: they are append-only logs).
* Any other DocType opts in by setting ``retention_days``. Its documents are
  deleted one by one through the normal delete pipeline, so hooks run, child
  rows go with them and the trash keeps a restorable snapshot (unless the
  DocType turns ``track_deletions`` off). At most MAX_DELETES_PER_RUN per
  DocType per night, oldest first.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import grunt
from grunt import log
from grunt.metadata.registry import doctype_registry
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task

if TYPE_CHECKING:
    from grunt.metadata.doctype import DocType

DEFAULT_LOG_RETENTION_DAYS = 30
MAX_DELETES_PER_RUN = 1000


def _date_field(dt: DocType) -> str:
    return dt.retention_date_field or "created_at"


async def _purge_log(dt: DocType, cutoff: datetime) -> int:
    return await grunt.db.delete(dt.name, {f"{_date_field(dt)}__lt": cutoff})


async def _purge_documents(dt: DocType, cutoff: datetime) -> int:
    field = _date_field(dt)
    names = await grunt.db.get_all(
        dt.name,
        filters={f"{field}__lt": cutoff},
        pluck="name",
        order_by=field,
        order="asc",
        limit=MAX_DELETES_PER_RUN,
    )

    session = grunt.get_session()
    deleted = 0
    for name in names:
        try:
            async with session.begin_nested():  # a failed delete rolls back alone
                await grunt.delete_doc(dt.name, name)
            deleted += 1
        except Exception as e:  # noqa: BLE001 - one undeletable doc must not stop the rest
            log.warning("retention.delete_failed", doctype=dt.name, name=name, error=str(e))
    return deleted


async def purge_doctype(dt: DocType, now: datetime, log_default: int) -> int:
    """Apply *dt*'s retention; returns how many documents were deleted."""
    if dt.is_virtual or dt.is_child or dt.is_singleton:
        return 0
    days = dt.retention_days or (log_default if dt.is_log else None)
    if not days:
        return 0
    cutoff = now - timedelta(days=days)
    purge = _purge_log if dt.is_log else _purge_documents
    deleted = await purge(dt, cutoff)
    if deleted:
        log.info("retention.purged", doctype=dt.name, deleted=deleted, days=days)
    return deleted


@retryable_task()
async def purge_expired_documents() -> None:
    """Delete everything past its DocType's retention (see module doc)."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    now = datetime.now(UTC)

    async with maker() as session, grunt.system_context(session, eng):
        from grunt.site.settings import get_setting

        log_default = await get_setting("log_retention_days", DEFAULT_LOG_RETENTION_DAYS)

        total = 0
        for dt in await doctype_registry.list_all():
            try:
                total += await purge_doctype(dt, now, log_default)
                await session.commit()
            except Exception as e:
                await session.rollback()
                log.warning("retention.purge_failed", doctype=dt.name, error=str(e))

        log.info("retention.done", total_deleted=total)
