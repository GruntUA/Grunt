"""Jinja2 filters for print templates."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any


def date_format(value: str | date | datetime | None, fmt: str = "%d.%m.%Y") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return value
        value = parsed
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    return str(value)


def datetime_format(value: str | datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            parsed_dt = datetime.fromisoformat(value)
        except ValueError:
            return value
        value = parsed_dt
    if isinstance(value, datetime):
        return value.strftime(fmt)
    return str(value)


def striptags(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"<[^>]+>", "", value)


def from_json(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError, TypeError:
        return {}


JINJA_FILTERS = {
    "date_format": date_format,
    "datetime_format": datetime_format,
    "striptags": striptags,
    "from_json": from_json,
}
