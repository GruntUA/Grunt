"""Flatten DocType ``calendar_view`` into flat ``calendar_*`` fields + a child table.

``calendar_view`` was a nested object ``{field, end_field, title_field, sources[]}``
edited by a bespoke Studio component (``CalendarSettings.vue``). It becomes three
plain Select fields — ``calendar_date_field``, ``calendar_end_date_field``,
``calendar_title_field`` — plus a ``calendar_sources`` child table backed by the
new ``DocTypeCalendarSource`` child DocType. ``DocType.calendar_view`` survives as
a read-only property.

Per stored DocType definition in ``grunt_meta_doctype``:
``data.calendar_view.field`` → ``data.calendar_date_field`` etc.,
``sources`` → ``calendar_sources`` (dropping the never-read ``remind_before_days``
sub-field), then the ``calendar_view`` key is removed. The DocType meta row's own
layout has the JSON editor swapped in place for the four fields.

Revision ID: 0015_flatten_calendar_view
Revises: 0014_flatten_gantt_view
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0015_flatten_calendar_view"
down_revision = "0014_flatten_gantt_view"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_VIEW_KEY_MAP = {
    "field": "calendar_date_field",
    "end_field": "calendar_end_date_field",
    "title_field": "calendar_title_field",
}

_TABLE_FIELD = {
    "fieldname": "calendar_sources",
    "label": "Додаткові джерела",
    "fieldtype": "Table",
    "options": "DocTypeCalendarSource",
    "description": "Інші типи документів, накладені на цей календар",
}
_CAL_LAYOUT_FIELDS = [
    {"fieldname": "calendar_date_field", "label": "Поле дати", "fieldtype": "Select",
     "options": "",
     "description": "Основне Date/Datetime-поле, за яким подія розміщується на календарі"},
    {"fieldname": "calendar_end_date_field", "label": "Поле дати завершення", "fieldtype": "Select",
     "options": "", "description": "Date/Datetime-поле кінця події (для багатоденних)"},
    {"fieldname": "calendar_title_field", "label": "Поле заголовка", "fieldtype": "Select",
     "options": "", "description": "Підпис події (default: поле заголовка)"},
    _TABLE_FIELD,
]


def _clean_source(src: dict) -> dict:
    return {k: v for k, v in src.items() if k != "remind_before_days"}


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

        if "calendar_view" in data:
            cv = data.pop("calendar_view", None)
            if isinstance(cv, dict):
                for old_k, new_k in _VIEW_KEY_MAP.items():
                    if cv.get(old_k) not in (None, ""):
                        data[new_k] = cv[old_k]
                sources = cv.get("sources") or []
                if sources:
                    data["calendar_sources"] = [
                        _clean_source(s) for s in sources if isinstance(s, dict)
                    ]
            changed = True

        fields = data.get("fields")
        if isinstance(fields, list):
            for i, f in enumerate(fields):
                if f.get("fieldname") == "calendar_view":
                    fields[i : i + 1] = [dict(x) for x in _CAL_LAYOUT_FIELDS]
                    changed = True
                    break

        if changed:
            conn.execute(tbl.update().where(tbl.c.name == row.name).values(data=data))
            converted += 1

    log.info("0015: flattened calendar_view on %d DocType definition(s)", converted)


def downgrade() -> None:
    # The nested shape is gone for good — irreversible.
    pass
