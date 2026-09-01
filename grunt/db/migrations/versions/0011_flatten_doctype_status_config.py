"""Flatten DocType ``status_config`` into ``status_field`` + ``status_indicators``.

The status display used to be a nested object ``status_config: {field, indicators}``
edited by a bespoke Studio component (``StatusSettings.vue``). It is now two plain
DocType fields — a Select (``status_field``) and a child table
(``status_indicators`` → ``DocTypeStatusIndicator``) — rendered by the generic
form, so the custom component is gone.

This migration rewrites every stored DocType definition in ``grunt_meta_doctype``:
``data.status_config.field`` → ``data.status_field`` and
``data.status_config.indicators`` → ``data.status_indicators``, then drops the
``status_config`` key.

Revision ID: 0011_flatten_doctype_status_config
Revises: 0010_drop_doctype_dashboard_tab
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0011_flatten_doctype_status_config"
down_revision = "0010_drop_doctype_dashboard_tab"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


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

        if "status_config" not in data:
            continue

        sc = data.pop("status_config", None)
        if isinstance(sc, dict):
            data["status_field"] = sc.get("field") or None
            data["status_indicators"] = sc.get("indicators") or []
        conn.execute(
            tbl.update().where(tbl.c.name == row.name).values(data=data)
        )
        converted += 1

    log.info("0011: flattened status_config on %d DocType definition(s)", converted)


def downgrade() -> None:
    # The nested shape is gone for good — irreversible.
    pass
