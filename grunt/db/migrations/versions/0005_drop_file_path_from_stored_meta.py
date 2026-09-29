"""Forget ``File.path`` / ``File.thumbnail_path`` in the stored DocType meta.

0004 dropped the columns, but the site's stored definition of File
(``grunt_meta_doctype``) still listed both fields: a core DocType's stored
fields that the JSON no longer has are kept as local customisations, so the
DocType-table sync that follows the migrations re-created the (now empty)
columns and the form kept showing «Storage path». Remove the fields from the
stored definition and drop the columns again.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-28
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_META = "grunt_meta_doctype"
_TABLE = "grunt_storage_file"
_GONE = ("path", "thumbnail_path")


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if _META in tables:
        meta = sa.table(_META, sa.column("name"), sa.column("data"))
        row = conn.execute(sa.select(meta.c.data).where(meta.c.name == "File")).first()
        if row is not None:
            data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            fields = data.get("fields") or []
            kept = [f for f in fields if f.get("fieldname") not in _GONE]
            if len(kept) != len(fields):
                data["fields"] = kept
                conn.execute(
                    sa.update(meta).where(meta.c.name == "File").values(data=json.dumps(data))
                )

    if _TABLE in tables:
        present = [c for c in _GONE if c in {col["name"] for col in inspector.get_columns(_TABLE)}]
        if present:
            with op.batch_alter_table(_TABLE) as batch:
                for column in present:
                    batch.drop_column(column)


def downgrade() -> None:
    pass
