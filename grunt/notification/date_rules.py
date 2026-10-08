"""Date-based notification rules - "N days before / after a date field".

A ``NotificationRule`` with event ``days_before`` / ``days_after`` is not
triggered by a save: once a day (08:00) :func:`check_date_rules` finds the
documents whose date field falls on the matching day and runs the rule on
them - contract ends, probation periods, certificate expiry; with
``every_year`` only day and month count (birthdays, work anniversaries).

A rule notifies about a document at most once per day, so a rerun of the job
(restart, second worker) sends nothing twice.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import grunt
from grunt import log
from grunt.config import settings
from grunt.tasks.broker import retryable_task

DATE_EVENTS = ("days_before", "days_after")
MAX_DOCS_PER_RULE = 100_000


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.default_timezone)


def local_today() -> date:
    return datetime.now(_tz()).date()


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """The local calendar *day* as a [start, end) UTC range."""
    start = datetime.combine(day, time.min, tzinfo=_tz()).astimezone(UTC)
    return start, start + timedelta(days=1)


def target_date(rule: dict[str, Any], today: date) -> date:
    """The date value a document needs today: before -> ahead, after -> behind."""
    days = int(rule.get("days") or 0)
    return (
        today + timedelta(days=days)
        if rule["event"] == "days_before"
        else today - timedelta(days=days)
    )


def _as_local_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(_tz()).date()
    if isinstance(value, date):
        return value
    text = str(value)
    return (
        _as_local_date(datetime.fromisoformat(text)) if len(text) > 10 else date.fromisoformat(text)
    )


def same_day_of_year(value: date, target: date) -> bool:
    """Day and month match; Feb 29 counts on Feb 28 in a non-leap year."""
    if (value.month, value.day) == (target.month, target.day):
        return True
    return (
        (value.month, value.day) == (2, 29)
        and (target.month, target.day) == (2, 28)
        and not calendar.isleap(target.year)
    )


async def due_documents(rule: dict[str, Any], today: date) -> list[dict[str, Any]]:
    """Documents of the rule's DocType whose date field matches today."""
    doctype, field = rule["ref_doctype"], rule["date_field"]
    meta = await grunt.get_meta(doctype)
    fdef = meta.get_field(field) if meta else None
    if fdef is None:
        log.warning("notification.date_rule_bad_field", rule=rule["name"], field=field)
        return []
    target = target_date(rule, today)

    if rule.get("every_year"):
        rows = await grunt.db.get_all(
            doctype, filters={f"{field}__isnull": False}, limit=MAX_DOCS_PER_RULE
        )
        return [
            r for r in rows if (d := _as_local_date(r.get(field))) and same_day_of_year(d, target)
        ]

    if fdef.fieldtype == "Date":
        filters: dict[str, Any] = {field: target}
    else:
        start, end = _day_bounds(target)
        filters = {f"{field}__gte": start, f"{field}__lt": end}
    return await grunt.db.get_all(doctype, filters=filters, limit=MAX_DOCS_PER_RULE)


async def run_rule(rule: dict[str, Any], today: date) -> int:
    """Notify about every due document not yet handled today; returns notifications sent."""
    from grunt.notification.service import notification_service

    session = grunt.get_session()
    since, _ = _day_bounds(today)
    sent = 0
    for doc in await due_documents(rule, today):
        already = await grunt.db.exists(
            "Notification",
            {
                "notification_rule": rule["name"],
                "doc_id": str(doc["name"]),
                "created_at__gte": since,
            },
        )
        if already:
            continue
        sent += await notification_service.apply_rule(
            session, rule, rule["ref_doctype"], dict(doc), "", rule["event"]
        )
    return sent


@retryable_task()
async def check_date_rules(today: str | None = None) -> int:
    """Daily job (08:00): run every enabled date-based rule. Returns notifications sent."""
    from grunt.site.manager import site_manager

    run_date = date.fromisoformat(today) if today else local_today()
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    total = 0
    async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
        rules = await grunt.db.get_all(
            "NotificationRule",
            filters={"event__in": list(DATE_EVENTS), "is_enabled": True},
            limit=1000,
        )
        for rule in rules:
            try:
                total += await run_rule(rule, run_date)
                await session.commit()
            except Exception:
                await session.rollback()
                log.exception("notification.date_rule_failed", rule=rule["name"])
    if total:
        log.info("notification.date_rules_sent", count=total, rules=len(rules))
    return total
