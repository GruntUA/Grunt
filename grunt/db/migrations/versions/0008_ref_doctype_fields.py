"""Rename the ``doctype`` field of reference DocTypes to ``ref_doctype``.

Every document serialises with a ``"doctype"`` key naming its own DocType
(``Document.as_dict``), so no DocType may have a field of that name: the
ActivityLog, Notification, Report, PrintFormat, ... field naming the DocType
they point at becomes ``ref_doctype``, as on EmailMessage.

Renames the column, the field in the stored definition (stored fields the
JSON no longer has are kept as local customisations - see 0005) and the
``doctype`` key of every DocType's ``calendar_sources`` rows.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-07
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from grunt.metadata.compiler import get_table_name

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_DOCTYPES = (
    "ActivityLog",
    "ClientScript",
    "DashboardChart",
    "Dashboard Widget",
    "DocTypeCalendarSource",
    "DocVersion",
    "Notification",
    "NotificationRule",
    "NumberCard",
    "PageWidget",
    "PrintFormat",
    "Report",
    "ServerScript",
    "ViewLog",
    "WebForm",
)
_OLD, _NEW = "doctype", "ref_doctype"


def _table_name(name: str, data: dict) -> str:
    return data.get("table_name") or get_table_name(data.get("module", ""), name)


def _rename_in_definition(name: str, data: dict) -> bool:
    changed = False
    if name in _DOCTYPES:
        for field in data.get("fields") or []:
            if field.get("fieldname") == _OLD:
                field["fieldname"] = _NEW
                changed = True
        for index in data.get("indexes") or []:
            if isinstance(index, list) and _OLD in index:
                index[index.index(_OLD)] = _NEW
                changed = True
    for source in data.get("calendar_sources") or []:
        if isinstance(source, dict) and _OLD in source:
            source[_NEW] = source.pop(_OLD)
            changed = True
    return changed


def _rename_column(conn: sa.Connection, table: str) -> None:
    columns = {c["name"] for c in sa.inspect(conn).get_columns(table)}
    if _OLD not in columns:
        return
    if _NEW in columns:
        # A DocType sync ran before this migration and added an empty column.
        t = sa.table(table, sa.column(_OLD), sa.column(_NEW))
        conn.execute(sa.update(t).where(t.c[_NEW].is_(None)).values({_NEW: t.c[_OLD]}))
        with op.batch_alter_table(table) as batch:
            batch.drop_column(_OLD)
    else:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(_OLD, new_column_name=_NEW)


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if _META not in tables:
        return

    meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON()))
    for name, raw in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not data:
            continue
        if name in _DOCTYPES:
            table = _table_name(name, data)
            if table in tables:
                _rename_column(conn, table)
        if _rename_in_definition(name, data):
            conn.execute(sa.update(meta).where(meta.c.name == name).values(definition=data))


def downgrade() -> None:
    pass
