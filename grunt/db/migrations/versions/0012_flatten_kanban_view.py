"""Flatten DocType ``kanban_view`` into a single ``kanban_column_field``.

``kanban_view`` was a nested object ``{column_field, title_field, color_field}``
edited by a bespoke Studio component (``KanbanSettings.vue``). Only
``column_field`` was ever read at runtime — the kanban title comes from the
DocType's own ``title_field`` and the colour from ``status_field``. It is now a
single plain Select field, ``kanban_column_field``, rendered by the generic
form, so the custom component is gone.

This migration rewrites every stored DocType definition in ``grunt_meta_doctype``:
``data.kanban_view.column_field`` → ``data.kanban_column_field``, then drops the
``kanban_view`` key.

Revision ID: 0012_flatten_kanban_view
Revises: 0011_flatten_doctype_status_config
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0012_flatten_kanban_view"
down_revision = "0011_flatten_doctype_status_config"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Replacement layout field (mirrors DocType.json) for the DocType meta row.
_KANBAN_SELECT_FIELD = {
    "fieldname": "kanban_column_field",
    "label": "Поле колонок",
    "fieldtype": "Select",
    "options": "",
    "description": (
        "Select-поле, за значеннями якого групуються колонки канбану "
        "(default: перше Select-поле у списку)"
    ),
}


def upgrade() -> None:
    conn = op.get_bind()
    meta = sa.MetaData()
    tbl = sa.Table("grunt_meta_doctype", meta, autoload_with=conn)

    converted = 0
    for row in conn.execute(sa.select(tbl.c.name, tbl.c.data)).fetchall():
        data = row.data
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            continue

        changed = False

        if "kanban_view" in data:
            kv = data.pop("kanban_view", None)
            if isinstance(kv, dict) and kv.get("column_field"):
                data["kanban_column_field"] = kv["column_field"]
            changed = True

        # The DocType meta row carries the old field in its own layout — swap
        # the JSON editor in place for the Select (matches DocType.json).
        fields = data.get("fields")
        if isinstance(fields, list):
            for i, f in enumerate(fields):
                if f.get("fieldname") == "kanban_view":
                    fields[i] = dict(_KANBAN_SELECT_FIELD)
                    changed = True
                    break

        if changed:
            conn.execute(tbl.update().where(tbl.c.name == row.name).values(data=data))
            converted += 1

    log.info("0012: flattened kanban_view on %d DocType definition(s)", converted)


def downgrade() -> None:
    # The nested shape is gone for good — irreversible.
    pass
