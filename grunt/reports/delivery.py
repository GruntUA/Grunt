"""Scheduled report delivery — email a ``Report`` as XLSX on a schedule.

A report opts in with ``schedule_frequency`` (Daily / Weekly / Monthly) and
``schedule_recipients``. The daily framework job (see
``grunt.tasks.scheduler._register_framework_jobs``) sends every report that is
due; the ``report.send_now`` form action sends one immediately.

The report runs as its owner, so row-level permissions apply exactly as they
would for that user in the UI (falls back to the system user when the owner is
not a real, active account — e.g. fixture-created reports).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import grunt
from grunt.i18n import _
from grunt.log import log
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.user import User

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def parse_recipients(raw: str | None) -> list[str]:
    """Split a comma / semicolon / newline separated address list."""
    return [r for r in (p.strip() for p in re.split(r"[,;\n]", raw or "")) if r]


def is_due(frequency: str | None, last_sent_at: datetime | str | None, today: date) -> bool:
    """Daily — not yet sent today; Weekly — 7+ days since the last send;
    Monthly — not yet sent this calendar month. Never sent → due."""
    if not frequency:
        return False
    if last_sent_at is None or last_sent_at == "":
        return True
    if isinstance(last_sent_at, str):
        last_sent_at = datetime.fromisoformat(last_sent_at.replace("Z", "+00:00"))
    last = last_sent_at.date()
    if frequency == "Daily":
        return last < today
    if frequency == "Weekly":
        return (today - last).days >= 7
    if frequency == "Monthly":
        return (last.year, last.month) < (today.year, today.month)
    return False


async def _run_as(report: dict[str, Any]) -> User:
    from grunt.auth.doctypes.User.user import SYSTEM_USER, get_user_by_email

    owner = await get_user_by_email(report.get("owner") or "")
    return owner if owner is not None and owner.is_active else SYSTEM_USER


async def send_report(report: dict[str, Any], session: AsyncSession) -> int:
    """Run *report*, queue it as XLSX to its recipients, stamp ``last_sent_at``.

    Returns the number of queued emails. Must run inside a system context.
    """
    from grunt.email.service import email_service
    from grunt.reports.engine import report_engine

    recipients = parse_recipients(report.get("schedule_recipients"))
    if not recipients:
        return 0

    name = report["report_name"]
    filters = report.get("schedule_filters") or {}
    result = await report_engine.run(name, filters, await _run_as(report), session)
    xlsx = await report_engine.export_excel(result, name)

    today = datetime.now(UTC).date().isoformat()
    rows = (result.get("meta") or {}).get("rows", len(result.get("data") or []))
    subject = _("Report “%(name)s”, %(date)s") % {"name": name, "date": today}
    body = _("Report “%(name)s” as of %(date)s: %(rows)s rows. The file is attached.") % {
        "name": name,
        "date": today,
        "rows": rows,
    }
    attachment = {"filename": f"{name[:50]}.xlsx", "mimetype": XLSX_MIMETYPE, "content": xlsx}

    for to in recipients:
        await email_service.queue_email(session, to, subject, body, attachments=[attachment])
    await grunt.db.set_value("Report", report["name"], "last_sent_at", datetime.now(UTC))
    log.info("reports.delivered", report=name, recipients=len(recipients), rows=rows)
    return len(recipients)


_REPORT_FIELDS = [
    "name",
    "owner",
    "report_name",
    "schedule_frequency",
    "schedule_recipients",
    "schedule_filters",
    "last_sent_at",
]


@retryable_task()
async def send_scheduled_reports() -> None:
    """Send every report whose schedule is due today."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    today = datetime.now(UTC).date()

    async with maker() as session, grunt.system_context(session, eng):
        reports = await grunt.db.get_all(
            "Report",
            filters={"schedule_frequency__in": ["Daily", "Weekly", "Monthly"]},
            fields=_REPORT_FIELDS,
            limit=None,
        )
        for report in reports:
            if not is_due(report["schedule_frequency"], report.get("last_sent_at"), today):
                continue
            try:
                await send_report(report, session)
                await session.commit()
            except Exception:
                await session.rollback()
                log.exception("reports.delivery_failed", report=report.get("report_name"))


async def send_report_now(name: str) -> int:
    """Send one report immediately, regardless of its schedule (form action)."""
    rows = await grunt.db.get_all("Report", filters={"name": name}, fields=_REPORT_FIELDS, limit=1)
    if not rows:
        grunt.throw(_("Report “%(name)s” not found") % {"name": name}, "NOT_FOUND")
    from grunt.local import require_session

    return await send_report(rows[0], require_session())
