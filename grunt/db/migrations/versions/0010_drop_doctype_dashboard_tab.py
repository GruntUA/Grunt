"""Drop the legacy "Дашборд" tab from the DocType metadata.

The tab held two fields — ``show_in_dashboard`` and ``dashboard_doctype`` —
that nothing in the framework ever read. The live mechanism for "related
document types shown on the form" is the ``links`` child table (the "Зв'язки"
tab), so the dashboard tab is pure dead metadata.

It only ever existed in the stored ``grunt_meta_doctype`` row (added via the
Studio builder on long-lived sites); the bundled ``DocType.json`` seed has no
such tab. ``_inject_core`` merges *new* JSON fields into the stored definition
but never removes stored-only ones, so ``grunt db migrate`` cannot clear it —
this migration does the surgical removal, once, on every site.

Revision ID: 0010_drop_doctype_dashboard_tab
Revises: 0009_drop_doc_type_permission
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0010_drop_doctype_dashboard_tab"
down_revision = "0009_drop_doc_type_permission"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_DROP_FIELDS = {"tab_dashboard", "show_in_dashboard", "dashboard_doctype"}


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
    log.info("0010: removed %d dashboard field(s) from DocType metadata", len(fields) - len(kept))


def downgrade() -> None:
    # The dashboard tab was dead metadata — not restored.
    pass
