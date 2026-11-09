"""Date buckets - group a date/datetime column by day, month, quarter or year.

The SQL lives on the dialect (``Dialect.date_bucket``); this module keeps a
by-name helper. The bucket names are query syntax - ``grunt.query.aggregates``.
"""

from typing import Any

from grunt.db.dialects import dialect_for


def date_bucket(column: Any, bucket: str, dialect: Any) -> Any:
    """SQL expression labelling *column* with its day / month / quarter / year.

    *dialect* - a name, engine, session or :class:`~grunt.db.dialects.Dialect`.
    """
    return dialect_for(dialect).date_bucket(column, bucket)
