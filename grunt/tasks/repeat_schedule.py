"""Auto Repeat schedule arithmetic - when a rule's next copy is due.

No dependencies: the ``AutoRepeat`` controller plans with it on save, and the
daily job (:mod:`grunt.tasks.auto_repeat`) moves the date forward with it.
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Any

MONTHS_BY_FREQUENCY = {"Monthly": 1, "Quarterly": 3, "Half-yearly": 6, "Yearly": 12}
FREQUENCIES = ("Daily", "Weekly", *MONTHS_BY_FREQUENCY)


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
