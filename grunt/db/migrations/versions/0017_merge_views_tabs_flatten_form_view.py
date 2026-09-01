"""Merge the two "Вигляди" tabs and flatten ``form_view`` → ``form_show_sidebar``.

The DocType form had two tabs labelled "Вигляди": the legacy ``tab_views``
(``experimental_component: ViewsTab`` — a Studio panel that, after every view
config became a flat field, only hosted the sidebar toggle) and
``tab_views_builder`` (the flat config sections). The Studio panel and its
components are gone; ``tab_views_builder`` is renamed to ``tab_views`` and is now
the single views tab.

``form_view`` was the last nested view-config object (only ``show_sidebar``):
it becomes a plain ``form_show_sidebar`` Check field.

Per stored DocType definition in ``grunt_meta_doctype``:
``data.form_view.show_sidebar`` → ``data.form_show_sidebar``; the ``form_view``
key is dropped. The DocType meta row's own layout drops the legacy ViewsTab tab,
renames the builder tab, and swaps the ``form_view`` JSON editor for the Check.

Revision ID: 0017_merge_views_tabs_flatten_form_view
Revises: 0016_flatten_list_view_quick_filters
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0017_merge_views_tabs_flatten_form_view"
down_revision = "0016_flatten_list_view_quick_filters"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_SIDEBAR_FIELD = {
    "fieldname": "form_show_sidebar",
    "label": "Бічна панель на формі",
    "fieldtype": "Check",
    "default": "1",
    "description": "Показувати панель деталей / тегів / зв'язків збоку від форми",
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

        if "form_view" in data:
            fv = data.pop("form_view", None)
            if isinstance(fv, dict) and isinstance(fv.get("show_sidebar"), bool):
                data["form_show_sidebar"] = fv["show_sidebar"]
            changed = True

        fields = data.get("fields")
        if isinstance(fields, list):
            new_fields = []
            for f in fields:
                fn = f.get("fieldname")
                # Drop the legacy Studio ViewsTab tab.
                if fn == "tab_views" and f.get("experimental_component") == "ViewsTab":
                    changed = True
                    continue
                # Drop the raw JSON form_view editor.
                if fn == "form_view" and f.get("fieldtype") == "Code":
                    new_fields.append(dict(_SIDEBAR_FIELD))
                    changed = True
                    continue
                # Promote the builder tab to be *the* views tab.
                if fn == "tab_views_builder":
                    f = {**f, "fieldname": "tab_views"}
                    changed = True
                new_fields.append(f)
            data["fields"] = new_fields

        if changed:
            conn.execute(tbl.update().where(tbl.c.name == row.name).values(data=data))
            converted += 1

    log.info("0017: merged views tabs / flattened form_view on %d DocType definition(s)", converted)


def downgrade() -> None:
    # The nested shape and the second tab are gone for good — irreversible.
    pass
