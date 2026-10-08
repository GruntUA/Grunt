"""Date buckets - group a date/datetime column by day, month, quarter or year."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, String, cast, func

DATE_BUCKETS = ("day", "month", "quarter", "year")


def date_bucket(column: Any, bucket: str, dialect: str) -> Any:
    """SQL expression labelling *column* with its day / month / quarter / year."""
    if dialect == "postgresql":
        fmt = {"day": "YYYY-MM-DD", "month": "YYYY-MM", "quarter": 'YYYY-"Q"Q', "year": "YYYY"}
        return func.to_char(column, fmt[bucket])
    # SQLite (and anything else with strftime)
    if bucket == "quarter":
        quarter = (cast(func.strftime("%m", column), Integer) + 2) // 3
        return func.strftime("%Y", column).op("||")("-Q").op("||")(cast(quarter, String))
    fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}
    return func.strftime(fmt[bucket], column)
