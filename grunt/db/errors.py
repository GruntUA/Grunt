"""Translate low-level database errors into user-friendly HTTP responses."""

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from grunt import _
from grunt.db.dialects import dialect_for
from grunt.document.meta import Meta


def _field_label(dt: Any, col_name: str) -> str:
    if dt is None:
        return col_name

    return Meta(dt).get_label(col_name)


def _unique_column(violation: Any) -> str | None:
    """The field a unique violation is about - reported, or read off our
    ``uq_<table>_<field>`` index name."""
    if violation.column:
        return violation.column
    prefix = f"uq_{violation.table}_" if violation.table else None
    if prefix and violation.constraint and violation.constraint.startswith(prefix):
        return violation.constraint.removeprefix(prefix)
    return None


def friendly_integrity_error(exc: IntegrityError, dt: Any, bind: Any) -> HTTPException:
    """Convert a DB ``IntegrityError`` into a user-friendly 422/409 HTTPException.

    *bind* - the session (or engine) the statement ran on: its dialect tells
    what was violated (``Dialect.integrity_violation``), and the message names
    the offending field's label rather than the raw driver text.
    """
    violation = dialect_for(bind).integrity_violation(exc)

    if violation and violation.kind == "not_null" and violation.column:
        label = _field_label(dt, violation.column)
        message = _("Field “%(label)s” is required and cannot be empty.") % {"label": _(label)}
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)

    col_name = _unique_column(violation) if violation and violation.kind == "unique" else None
    if col_name and dt is not None:
        label = _field_label(dt, col_name)
        message = _("The value of field “%(label)s” already exists. Enter a unique value.") % {
            "label": _(label)
        }
    else:
        message = _("A record with this value already exists. Enter a unique value.")

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
