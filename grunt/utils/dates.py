"""Dates in the site's time zone and relative date tokens.

A filter value on a date field may be relative to the day it is applied:
``today``, ``today-30``, ``today+7`` (days). A saved filter, a report
condition or a link keeps the token, so "overdue" stays overdue tomorrow
instead of freezing on the day it was saved.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from grunt.config import settings

RELATIVE_DATE = re.compile(r"^today(?:\s*([+-])\s*(\d{1,5}))?$", re.IGNORECASE)


def site_timezone() -> ZoneInfo:
    return ZoneInfo(settings.default_timezone)


def local_today() -> date:
    """Today in the site's time zone."""
    return datetime.now(site_timezone()).date()


def relative_date(value: Any) -> date | None:
    """The day a ``today`` / ``today±N`` token stands for (site time zone),
    ``None`` for anything else."""
    if not isinstance(value, str):
        return None
    m = RELATIVE_DATE.match(value.strip())
    if m is None:
        return None
    days = int(m.group(2) or 0) * (-1 if m.group(1) == "-" else 1)
    return local_today() + timedelta(days=days)


def local_day_start(day: date) -> datetime:
    """Midnight of the local calendar *day*, in UTC - where a datetime
    comparison with that day starts."""
    return datetime.combine(day, time.min, tzinfo=site_timezone()).astimezone(UTC)
