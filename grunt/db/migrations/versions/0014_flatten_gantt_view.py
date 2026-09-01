"""Flatten DocType ``gantt_view`` into flat ``gantt_*`` fields.

``gantt_view`` was a nested object edited by a bespoke Studio component
(``GanttSettings.vue``). Its members are all scalars (plus a ``color_map``
dict), so it becomes eight plain fields — ``gantt_start_field``,
``gantt_end_field``, ``gantt_title_field``, ``gantt_progress_field``,
``gantt_color_field``, ``gantt_color_map``, ``gantt_default_color``,
``gantt_dependencies_field`` — rendered by the generic form.
``DocType.gantt_view`` survives as a read-only property.

This migration rewrites every stored DocType definition in ``grunt_meta_doctype``:
each ``data.gantt_view.<k>`` → ``data.gantt_<k>``, then drops the ``gantt_view``
key. The DocType meta row also carries the old JSON editor in its layout — that
field is swapped in place for the eight fields.

Revision ID: 0014_flatten_gantt_view
Revises: 0013_flatten_tree_view
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0014_flatten_gantt_view"
down_revision = "0013_flatten_tree_view"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_KEYS = (
    "start_field",
    "end_field",
    "title_field",
    "progress_field",
    "color_field",
    "color_map",
    "default_color",
    "dependencies_field",
)

# Replacement layout fields (mirror DocType.json) for the DocType meta row.
_GANTT_LAYOUT_FIELDS = [
    {"fieldname": "gantt_start_field", "label": "Поле початку", "fieldtype": "Select",
     "options": "", "description": "Date/Datetime-поле, де починається смуга"},
    {"fieldname": "gantt_end_field", "label": "Поле завершення", "fieldtype": "Select",
     "options": "", "description": "Date/Datetime-поле, де смуга закінчується"},
    {"fieldname": "gantt_title_field", "label": "Поле заголовка", "fieldtype": "Select",
     "options": "", "description": "Підпис рядка/смуги (default: поле заголовка)"},
    {"fieldname": "gantt_progress_field", "label": "Поле прогресу (0–100)", "fieldtype": "Select",
     "options": "", "description": "Float/Int/Percent — заповнення смуги"},
    {"fieldname": "gantt_color_field", "label": "Колір за полем", "fieldtype": "Select",
     "options": ""},
    {"fieldname": "gantt_color_map", "label": "Мапа кольорів", "fieldtype": "JSON",
     "depends_on": "gantt_color_field",
     "description": "{\"В роботі\": \"#f59e0b\", \"Готово\": \"#16a34a\"}"},
    {"fieldname": "gantt_default_color", "label": "Колір за замовчуванням", "fieldtype": "Data",
     "description": "#2563eb або var(--primary)"},
    {"fieldname": "gantt_dependencies_field", "label": "Поле залежностей", "fieldtype": "Select",
     "options": "",
     "description": (
         "Текстове поле зі списком name документів-попередників через кому "
         "— між ними малюються стрілки"
     )},
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

        if "gantt_view" in data:
            gv = data.pop("gantt_view", None)
            if isinstance(gv, dict):
                for k in _KEYS:
                    if gv.get(k) not in (None, "", {}):
                        data[f"gantt_{k}"] = gv[k]
            changed = True

        fields = data.get("fields")
        if isinstance(fields, list):
            for i, f in enumerate(fields):
                if f.get("fieldname") == "gantt_view":
                    fields[i : i + 1] = [dict(x) for x in _GANTT_LAYOUT_FIELDS]
                    changed = True
                    break

        if changed:
            conn.execute(tbl.update().where(tbl.c.name == row.name).values(data=data))
            converted += 1

    log.info("0014: flattened gantt_view on %d DocType definition(s)", converted)


def downgrade() -> None:
    # The nested shape is gone for good — irreversible.
    pass
