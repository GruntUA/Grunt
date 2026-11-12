"""Deliver personal reminders (``Reminder``) whose time has come - every minute.

Each due row is claimed atomically (``notified`` False -> True) before the
notification goes out, so overlapping runs never remind twice.
"""

from datetime import UTC, datetime
from typing import Any

from grunt.db.api import GruntDB
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.tasks.broker import retryable_task
lazy from grunt.document.titles import resolve_reference_titles
lazy from grunt.notification.events import trigger
lazy from grunt.site.manager import site_manager

_db = GruntDB()  # stateless: reads through the context's session


async def _title(row: dict[str, Any]) -> str:
    doctype, name = row.get("reference_doctype"), row.get("reference_name")
    if not doctype or not name:
        return ""

    titles = await resolve_reference_titles([(doctype, str(name))])
    return titles.get((doctype, str(name))) or str(name)


async def deliver(row: dict[str, Any]) -> bool:
    """Claim and send one reminder; False when another run already took it,
    or when its notification reached nobody (it is retried)."""

    claimed = await _db.bulk_update(
        "Reminder", {"name": row["name"], "notified": False}, {"notified": True}
    )
    if not claimed:
        return False

    title = await _title(row)
    result = await trigger(
        "grunt.reminder",
        doc=row,
        doctype="Reminder",
        link=(row.get("reference_doctype") or "", str(row.get("reference_name") or "")),
        extra={"title": title, "note": (row.get("description") or "").strip()},
        session=require_session(),
    )
    if result.rules and not result.notified:
        # A rule ran but no channel reached anyone (e.g. an email-only rule
        # with the queue failing) - leave it unsent, the next run retries.
        # No enabled rule at all is a choice, not a failure.
        await _db.bulk_update("Reminder", {"name": row["name"]}, {"notified": False})
        return False
    return True


async def process_due(now: datetime | None = None) -> int:
    """Send every unsent reminder due by *now*; runs inside a system context."""
    now = now or datetime.now(UTC)
    rows = await _db.get_all(
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
            await require_session().commit()
        except Exception:
            await require_session().rollback()
            log.exception("reminder.delivery_failed", reminder=row["name"])
    if sent:
        log.info("reminders.sent", count=sent)
    return sent


@retryable_task()
async def send_reminders() -> int:
    """Scheduler entry point (every minute)."""

    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, system_context(session, site_manager.get_engine(site)):
        return await process_due()
