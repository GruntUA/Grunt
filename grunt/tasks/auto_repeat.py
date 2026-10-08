"""Auto Repeat - create copies of a template document on a schedule.

An ``AutoRepeat`` rule points at a template document; once a day
:func:`run_auto_repeats` copies it for every rule whose ``next_schedule_date``
has come, then moves the date forward. Copies are created **as the rule's
owner**, so the owner's create permission (and the DocType's controllers and
hooks) apply exactly as if they had pressed "Duplicate" themselves.

Missed days (server down) are caught up, at most :data:`MAX_CATCH_UP` copies
per rule per run.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Any

import grunt
from grunt import _, log
from grunt.tasks.broker import retryable_task

MONTHS_BY_FREQUENCY = {"Monthly": 1, "Quarterly": 3, "Half-yearly": 6, "Yearly": 12}
FREQUENCIES = ("Daily", "Weekly", *MONTHS_BY_FREQUENCY)
MAX_CATCH_UP = 12

# Never copied from the template: identity, audit and per-user state.
_SKIP_FIELDS = frozenset(
    {"id", "name", "owner", "created_at", "modified_at", "modified_by", "_seen", "_liked_by"}
)


# Schedule arithmetic


def as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _on_day(year: int, month: int, day: int | None, last_day: bool) -> date:
    """*day* of the month, clamped to its length (``last_day`` -> the last one)."""
    days_in_month = calendar.monthrange(year, month)[1]
    return date(year, month, days_in_month if last_day else min(day or 1, days_in_month))


def next_date(current: date, frequency: str, day: int | None, last_day: bool) -> date:
    """The occurrence after *current*.

    Monthly-type schedules recompute the day from the anchor every time, so a
    rule on the 31st goes Jan 31 -> Feb 28 -> Mar 31 instead of drifting.
    """
    if frequency == "Daily":
        return current + timedelta(days=1)
    if frequency == "Weekly":
        return current + timedelta(weeks=1)
    months = MONTHS_BY_FREQUENCY[frequency]
    index = current.year * 12 + current.month - 1 + months
    return _on_day(index // 12, index % 12 + 1, day, last_day)


def first_date(
    start: date, frequency: str, day: int | None, last_day: bool, not_before: date
) -> date:
    """First occurrence on or after both *start* and *not_before*."""
    candidate = start
    if frequency in MONTHS_BY_FREQUENCY:
        candidate = _on_day(start.year, start.month, day or start.day, last_day)
        if candidate < start:
            candidate = next_date(candidate, frequency, day or start.day, last_day)
    while candidate < not_before:
        candidate = next_date(candidate, frequency, day or start.day, last_day)
    return candidate


def anchor_day(rule: dict[str, Any]) -> int | None:
    """The day of month monthly-type schedules land on."""
    start = as_date(rule.get("start_date"))
    return rule.get("repeat_on_day") or (start.day if start else None)


def status_for(rule: dict[str, Any], next_on: date | None) -> str:
    if rule.get("disabled"):
        return "Disabled"
    end = as_date(rule.get("end_date"))
    if next_on is None or (end is not None and next_on > end):
        return "Completed"
    return "Active"


# Copying


async def create_copy(rule: dict[str, Any], on_date: date) -> dict[str, Any]:
    """Insert one copy of the rule's template document, as the current user."""
    from grunt.workflow.registry import get_active_workflow

    doctype = rule["reference_doctype"]
    template = await grunt.get_doc(doctype, rule["reference_document"])
    data = {k: v for k, v in template.items() if k not in _SKIP_FIELDS}

    # A copy starts its own workflow from the initial state.
    workflow = await get_active_workflow(doctype)
    if workflow:
        data.pop(workflow.state_field, None)

    meta = await grunt.get_meta(doctype)
    if rule.get("date_field"):
        data[rule["date_field"]] = on_date.isoformat()
    if meta is not None and meta.has_field("auto_repeat"):
        data["auto_repeat"] = rule["name"]
    return await grunt.new_doc(doctype, data)


async def _owner(email: str) -> Any:
    from grunt.auth.doctypes.User.user import get_auth_context_user

    user = await get_auth_context_user(email)
    return user if user is not None and user.is_active else None


async def _notify(rule: dict[str, Any], subject: str, message: str) -> None:
    if not rule.get("notify") or not rule.get("owner"):
        return
    from grunt.notification.service import notification_service

    try:
        await notification_service.notify(
            grunt.get_session(),
            user=rule["owner"],
            doctype="AutoRepeat",
            doc_id=rule["name"],
            subject=subject,
            message=message,
        )
    except Exception:
        log.warning("auto_repeat.notify_failed", rule=rule["name"])


async def process_rule(name: str, today: date) -> int:
    """Create every copy *name* is due for (up to :data:`MAX_CATCH_UP`).

    Runs inside a system context; returns the number of copies created. Each
    copy is committed on its own, so one failure keeps the earlier ones.
    """
    session = grunt.get_session()
    rule = await grunt.get_doc("AutoRepeat", name)
    frequency = rule["frequency"]
    day, last_day = anchor_day(rule), bool(rule.get("repeat_on_last_day"))
    end = as_date(rule.get("end_date"))
    next_on = as_date(rule.get("next_schedule_date"))

    updates: dict[str, Any] = {"last_run_at": datetime.now(UTC)}
    created = 0
    error: str | None = None

    owner = await _owner(rule["owner"])
    if owner is None:
        error = _("The owner of this rule is missing or inactive")

    while (
        owner is not None
        and next_on is not None
        and next_on <= today
        and (end is None or next_on <= end)
        and created < MAX_CATCH_UP
    ):
        try:
            async with grunt.context(session, grunt.get_engine(), owner):
                copy = await create_copy(rule, next_on)
            await session.commit()
        except Exception as e:
            await session.rollback()
            error = getattr(e, "message", None) or getattr(e, "detail", None) or str(e)
            log.warning("auto_repeat.copy_failed", rule=name, error=error)
            break
        created += 1
        updates["last_document"] = copy["name"]
        log.info("auto_repeat.copy_created", rule=name, doc=copy["name"], on=str(next_on))
        await _notify(
            rule,
            _("Created %(doctype)s %(name)s")
            % {"doctype": _(rule["reference_doctype"]), "name": copy["name"]},
            _("Auto repeat %(rule)s") % {"rule": name},
        )
        next_on = next_date(next_on, frequency, day, last_day)

    if error:
        await _notify(rule, _("Auto repeat %(rule)s failed") % {"rule": name}, error)

    updates.update(
        next_schedule_date=next_on,
        status=status_for(rule, next_on),
        created_count=int(rule.get("created_count") or 0) + created,
        last_error=error,
    )
    await grunt.db.set_value("AutoRepeat", name, updates)
    await session.commit()
    return created


@retryable_task()
async def run_auto_repeats(today: str | None = None) -> int:
    """Daily job: process every active rule that is due. Returns copies created."""
    from grunt.site.manager import site_manager

    run_date = as_date(today) or date.today()
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    engine = site_manager.get_engine(site)
    total = 0
    async with maker() as session, grunt.system_context(session, engine):
        due = await grunt.db.get_all(
            "AutoRepeat",
            filters={"status": "Active", "next_schedule_date__lte": run_date},
            fields=["name"],
            limit=10_000,
        )
        for row in due:
            try:
                total += await process_rule(row["name"], run_date)
            except Exception:
                await session.rollback()
                log.exception("auto_repeat.rule_failed", rule=row["name"])
    log.info("auto_repeat.run_done", rules=len(due), created=total)
    return total
