"""Flatten DocType ``tree_view`` into flat ``tree_*`` fields.

``tree_view`` was a nested object ``{parent_field, title_field, as_of_date_field,
sort_by, sort_order}`` edited by a bespoke Studio component (``TreeSettings.vue``).
It is now five plain fields — ``tree_parent_field``, ``tree_title_field``,
``tree_as_of_date_field``, ``tree_sort_by``, ``tree_sort_order`` — rendered by the
generic form. ``DocType.tree_view`` survives as a read-only property that
re-assembles the object for the backend tree service.

This migration rewrites every stored DocType definition in ``grunt_meta_doctype``:
each ``data.tree_view.<k>`` → ``data.tree_<k>`` (``parent_field`` →
``tree_parent_field`` etc.), then drops the ``tree_view`` key. The DocType meta
row also carries the old JSON editor in its own layout — that field is swapped
in place for the five Selects.

Revision ID: 0013_flatten_tree_view
Revises: 0012_flatten_kanban_view
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0013_flatten_tree_view"
down_revision = "0012_flatten_kanban_view"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_KEY_MAP = {
    "parent_field": "tree_parent_field",
    "title_field": "tree_title_field",
    "as_of_date_field": "tree_as_of_date_field",
    "sort_by": "tree_sort_by",
    "sort_order": "tree_sort_order",
}

# Replacement layout fields (mirror DocType.json) for the DocType meta row.
_TREE_LAYOUT_FIELDS = [
    {
        "fieldname": "tree_parent_field",
        "label": "Батьківське поле",
        "fieldtype": "Select",
        "options": "",
        "depends_on": "is_tree",
        "description": "Link-поле, що вказує на цей самий DocType (ієрархія вузлів)",
    },
    {
        "fieldname": "tree_title_field",
        "label": "Поле назви вузла",
        "fieldtype": "Select",
        "options": "",
        "depends_on": "is_tree",
        "description": "Яке поле показувати як підпис вузла (default: поле заголовка)",
    },
    {
        "fieldname": "tree_as_of_date_field",
        "label": "Поле дати «станом на»",
        "fieldtype": "Select",
        "options": "",
        "depends_on": "is_tree",
        "description": "Date-поле, що вмикає вибір дати в панелі дерева",
    },
    {
        "fieldname": "tree_sort_by",
        "label": "Сортувати за",
        "fieldtype": "Select",
        "options": "",
        "depends_on": "is_tree",
    },
    {
        "fieldname": "tree_sort_order",
        "label": "Напрям сортування",
        "fieldtype": "Select",
        "options": "asc\ndesc",
        "default": "asc",
        "depends_on": "is_tree",
    },
]


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

        if "tree_view" in data:
            tv = data.pop("tree_view", None)
            if isinstance(tv, dict):
                for old_k, new_k in _KEY_MAP.items():
                    if tv.get(old_k) not in (None, ""):
                        data[new_k] = tv[old_k]
            changed = True

        fields = data.get("fields")
        if isinstance(fields, list):
            for i, f in enumerate(fields):
                if f.get("fieldname") == "tree_view":
                    fields[i : i + 1] = [dict(x) for x in _TREE_LAYOUT_FIELDS]
                    changed = True
                    break

        if changed:
            conn.execute(tbl.update().where(tbl.c.name == row.name).values(data=data))
            converted += 1

    log.info("0013: flattened tree_view on %d DocType definition(s)", converted)


def downgrade() -> None:
    # The nested shape is gone for good — irreversible.
    pass
