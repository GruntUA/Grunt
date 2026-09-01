"""Drop the dead "Картка" and "Керованість" tabs from the DocType metadata.

A bad merge (commit 3063f36) re-appended a stale schema block to the end of
``DocType.json``. Later flatten migrations cleaned up most of it, but three
empty containers survived:

* ``tab_card`` ("Картка") — the ``actions`` and ``links`` child tables that
  used to live under it were moved to the dedicated ``tab_actions`` ("Дії")
  and ``tab_links`` ("Зв'язки") tabs, leaving "Картка" empty.
* ``tab_settings`` ("Керованість") together with its now-empty
  ``sec_naming`` / ``sec_flags`` sections and their bare columns — every
  field they once held moved to "Загальне" and "Поведінка".

``DocType.json`` has already been fixed. ``_inject_core`` merges *new* JSON
fields into the stored ``grunt_meta_doctype`` row and reorders known fields,
but never removes stored-only ones — so ``grunt db migrate`` cannot clear the
leftovers. This migration does the surgical removal, once, on every site.

Revision ID: 0018_drop_doctype_dead_tabs
Revises: 0017_merge_views_tabs_flatten_form_view
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0018_drop_doctype_dead_tabs"
down_revision = "0017_merge_views_tabs_flatten_form_view"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_DROP_FIELDS = {
    "tab_card",
    "tab_settings",
    "sec_naming",
    "col_n1",
    "col_n2",
    "sec_flags",
    "col_f1",
    "col_f2",
}


def upgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT data FROM grunt_meta_doctype WHERE name = 'DocType'")
    ).first()
    if row is None:
        return

    raw = row[0]
    data: dict = json.loads(raw) if isinstance(raw, str) else dict(raw)

    fields = data.get("fields", [])
    kept = [f for f in fields if f.get("fieldname") not in _DROP_FIELDS]
    if len(kept) == len(fields):
        return  # already clean

    data["fields"] = kept
    conn.execute(
        sa.text("UPDATE grunt_meta_doctype SET data = :data WHERE name = 'DocType'"),
        {"data": json.dumps(data, ensure_ascii=False)},
    )
    log.info(
        "0018: removed %d dead tab/section field(s) from DocType metadata",
        len(fields) - len(kept),
    )


def downgrade() -> None:
    # Dead metadata — not restored.
    pass
