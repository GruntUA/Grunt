"""Flatten DocType ``list_view`` — lift ``fast_filters`` to ``quick_filters``.

``list_view`` was a nested object; its ``fields`` / ``sort_by`` / ``sort_order``
/ ``default_filters`` members were never read anywhere, and ``fast_filters`` (the
list/tree toolbar filter set) is renamed to ``quick_filters`` and moved up as a
child table backed by the new ``DocTypeQuickFilter`` child DocType. It is edited
in the generic form, so the bespoke ``ListViewSettings.vue`` is gone.

Per stored DocType definition in ``grunt_meta_doctype``:
``data.list_view.fast_filters`` (or ``.quick_filters``) → ``data.quick_filters``,
then the ``list_view`` key is removed. The DocType meta row's own layout has the
JSON editor swapped in place for the ``quick_filters`` table.

Revision ID: 0016_flatten_list_view_quick_filters
Revises: 0015_flatten_calendar_view
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0016_flatten_list_view_quick_filters"
down_revision = "0015_flatten_calendar_view"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_TABLE_FIELD = {
    "fieldname": "quick_filters",
    "label": "Швидкі фільтри",
    "fieldtype": "Table",
    "options": "DocTypeQuickFilter",
    "description": "Фільтри у панелі списку/дерева",
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

        if "list_view" in data:
            lv = data.pop("list_view", None)
            if isinstance(lv, dict):
                qf = lv.get("fast_filters") or lv.get("quick_filters")
                if qf:
                    data["quick_filters"] = qf
            changed = True

        fields = data.get("fields")
        if isinstance(fields, list):
            for i, f in enumerate(fields):
                if f.get("fieldname") == "list_view":
                    fields[i : i + 1] = [dict(_TABLE_FIELD)]
                    changed = True
                    break
                if f.get("fieldname") == "quick_filters" and f.get("fieldtype") != "Table":
                    fields[i] = dict(_TABLE_FIELD)
                    changed = True

        if changed:
            conn.execute(tbl.update().where(tbl.c.name == row.name).values(data=data))
            converted += 1

    log.info("0016: flattened list_view on %d DocType definition(s)", converted)


def downgrade() -> None:
    # The nested shape is gone for good — irreversible.
    pass
