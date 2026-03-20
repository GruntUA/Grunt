"""Jinja2 filters for print templates."""

from __future__ import annotations

import re
from datetime import date, datetime


def date_format(value: str | date | datetime | None, fmt: str = "%d.%m.%Y") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    return str(value)


def datetime_format(
    value: str | datetime | None, fmt: str = "%d.%m.%Y %H:%M"
) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime(fmt)
    return str(value)


def striptags(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"<[^>]+>", "", value)


JINJA_FILTERS = {
    "date_format": date_format,
    "datetime_format": datetime_format,
    "striptags": striptags,
}
