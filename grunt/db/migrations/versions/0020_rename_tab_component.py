"""Rename the field property ``experimental_component`` → ``tab_component``.

The prop is now a stable part of the metadata model (a Tab field naming the Vue
component that renders its body — ``DesignerTab``, ``WorkflowGraphTab``), so it
loses the "experimental" name. ``DocType.json`` / ``Workflow.json`` and the
``DocField`` model already use the new name; the property is also in
``_CORE_SYNCED_FIELD_ATTRS`` now, so core rows self-heal on next load — but
Studio-customised rows won't, hence this one-shot rename across every stored
DocType.

Unknown keys are ignored by ``DocField`` (no ``extra="forbid"``), so a stray
``experimental_component`` would be harmless; this just keeps the stored JSON
clean. ``data`` normalisation / double-encoding repair is 0019's job — this
migration only rewrites a row when it actually renames a key.

Revision ID: 0020_rename_tab_component
Revises: 0019_drop_doctype_quick_filters
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0020_rename_tab_component"
down_revision = "0019_drop_doctype_quick_filters"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_OLD = "experimental_component"
_NEW = "tab_component"


def _as_dict(raw: object) -> dict | None:
    value = raw
    for _ in range(4):
        if isinstance(value, dict):
            return value
        if isinstance(value, (str, bytes)):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return None
        else:
            return None
    return None


def upgrade() -> None:
    conn = op.get_bind()
    meta = sa.MetaData()
    tbl = sa.Table("grunt_meta_doctype", meta, autoload_with=conn)

    converted = 0
    for row in conn.execute(sa.select(tbl.c.name, tbl.c.data)).fetchall():
        data = _as_dict(row.data)
        if data is None:
            continue

        changed = False
        for field in data.get("fields", []):
            if isinstance(field, dict) and _OLD in field:
                field[_NEW] = field.pop(_OLD)
                changed = True

        if changed:
            conn.execute(tbl.update().where(tbl.c.name == row.name).values(data=data))
            converted += 1

    log.info("0020: renamed %s→%s on %d DocType definition(s)", _OLD, _NEW, converted)


def downgrade() -> None:
    conn = op.get_bind()
    meta = sa.MetaData()
    tbl = sa.Table("grunt_meta_doctype", meta, autoload_with=conn)

    for row in conn.execute(sa.select(tbl.c.name, tbl.c.data)).fetchall():
        data = _as_dict(row.data)
        if data is None:
            continue
        changed = False
        for field in data.get("fields", []):
            if isinstance(field, dict) and _NEW in field:
                field[_OLD] = field.pop(_NEW)
                changed = True
        if changed:
            conn.execute(tbl.update().where(tbl.c.name == row.name).values(data=data))
