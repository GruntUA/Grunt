"""PrintFormat ``is_app_format`` -> ``is_standard`` (standard records).

PrintFormat became a ``standard_records`` DocType: an app's print formats are
its standard records, saved to ``<app>/<module>/records/print_format/`` like
any other. The flag takes the shared name; the stored definition forgets the
old field (stored fields the JSON no longer has are kept - see 0005).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-07
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_TABLE = "grunt_print_format"
_OLD, _NEW = "is_app_format", "is_standard"


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if _META in tables:
        meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON()))
        row = conn.execute(sa.select(meta.c.definition).where(meta.c.name == "PrintFormat")).first()
        data = (json.loads(row[0]) if isinstance(row[0], str) else row[0]) if row else None
        if data:
            fields = data.get("fields") or []
            if any(f.get("fieldname") == _NEW for f in fields):
                data["fields"] = [f for f in fields if f.get("fieldname") != _OLD]
            else:
                for f in fields:
                    if f.get("fieldname") == _OLD:
                        f["fieldname"] = _NEW
            conn.execute(
                sa.update(meta).where(meta.c.name == "PrintFormat").values(definition=data)
            )

    if _TABLE not in tables:
        return
    columns = {c["name"] for c in sa.inspect(conn).get_columns(_TABLE)}
    if _OLD not in columns:
        return
    if _NEW in columns:
        t = sa.table(_TABLE, sa.column(_OLD), sa.column(_NEW))
        conn.execute(sa.update(t).where(t.c[_OLD].is_(True)).values({_NEW: True}))
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_OLD)
    else:
        with op.batch_alter_table(_TABLE) as batch:
            batch.alter_column(_OLD, new_column_name=_NEW)


def downgrade() -> None:
    pass
