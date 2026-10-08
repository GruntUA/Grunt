"""Deliver personal reminders (``Reminder``) whose time has come - every minute.

Each due row is claimed atomically (``notified`` False -> True) before the
notification goes out, so overlapping runs never remind twice.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import grunt
from grunt import _, log
from grunt.i18n import language_of, use_language
from grunt.tasks.broker import retryable_task


async def _title(row: dict[str, Any]) -> str:
    doctype, name = row.get("reference_doctype"), row.get("reference_name")
    if not doctype or not name:
        return ""
    from grunt.document.titles import resolve_reference_titles

    titles = await resolve_reference_titles([(doctype, str(name))])
    return titles.get((doctype, str(name))) or str(name)


async def deliver(row: dict[str, Any]) -> bool:
    """Claim and send one reminder; False when another run already took it."""
    from grunt.notification.service import notification_service

    claimed = await grunt.db.bulk_update(
        "Reminder", {"name": row["name"], "notified": False}, {"notified": True}
    )
    if not claimed:
        return False

    user = row["owner"]
    note = (row.get("description") or "").strip()
    with use_language(await language_of(user)):
        title = await _title(row)
        subject = _("Reminder: %(title)s") % {"title": title} if title else _("Reminder")
        message = note or title or _("You asked to be reminded")
    await notification_service.notify(
        grunt.get_session(),
        user=user,
        doctype=row.get("reference_doctype") or "Reminder",
        doc_id=str(row.get("reference_name") or row["name"]),
        subject=subject,
        message=message,
    )
    return True


async def process_due(now: datetime | None = None) -> int:
    """Send every unsent reminder due by *now*; runs inside a system context."""
    now = now or datetime.now(UTC)
    rows = await grunt.db.get_all(
        "Reminder",
        filters={"notified": False, "remind_at__lte": now},
        fields=["name", "owner", "remind_at", "description", "reference_doctype", "reference_name"],
        order_by="remind_at",
        order="asc",
        limit=1000,
    )
    sent = 0
    for row in rows:
        try:
            sent += await deliver(row)
            await grunt.get_session().commit()
        except Exception:
            await grunt.get_session().rollback()
            log.exception("reminder.delivery_failed", reminder=row["name"])
    if sent:
        log.info("reminders.sent", count=sent)
    return sent


@retryable_task()
async def send_reminders() -> int:
    """Scheduler entry point (every minute)."""
    from grunt.site.manager import site_manager

    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
        return await process_due()
