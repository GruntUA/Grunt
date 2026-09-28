"""Translate low-level database errors into user-friendly HTTP responses."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from grunt.i18n import _

_NOT_NULL_RE = re.compile(r"NOT NULL constraint failed:\s*\S+\.(\w+)", re.IGNORECASE)
_UNIQUE_SQLITE_RE = re.compile(r"UNIQUE constraint failed:\s*\S+\.(\w+)", re.IGNORECASE)
# PostgreSQL via constraint name: uq_{table}_{fieldname}
_UNIQUE_POSTGRES_RE = re.compile(r'"uq_[^"]+?_(\w+)"')


def _field_label(dt: Any, col_name: str) -> str:
    if dt is None:
        return col_name
    from grunt.document.meta import Meta

    return Meta(dt).get_label(col_name)


def friendly_integrity_error(exc: IntegrityError, dt: Any) -> HTTPException:
    """Convert a DB ``IntegrityError`` into a user-friendly 422/409 HTTPException.

    Recognizes SQLite and PostgreSQL wording for NOT NULL and UNIQUE constraint
    violations and reports the offending field's label rather than the raw
    driver message.
    """
    raw = str(exc.orig or exc)

    m_nn = _NOT_NULL_RE.search(raw)
    if m_nn:
        label = _field_label(dt, m_nn.group(1))
        message = _("Field “%(label)s” is required and cannot be empty.") % {"label": _(label)}
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)

    col_name: str | None = None
    m = _UNIQUE_SQLITE_RE.search(raw)
    if m:
        col_name = m.group(1)
    else:
        m2 = _UNIQUE_POSTGRES_RE.search(raw)
        if m2:
            col_name = m2.group(1)

    if col_name and dt is not None:
        label = _field_label(dt, col_name)
        message = _("The value of field “%(label)s” already exists. Enter a unique value.") % {
            "label": _(label)
        }
    else:
        message = _("A record with this value already exists. Enter a unique value.")

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
