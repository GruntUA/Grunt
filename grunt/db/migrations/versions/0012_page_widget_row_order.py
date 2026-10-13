"""Page widgets are ordered by their rows, not by ``PageWidget.sequence``.

The dashboard sorted widgets by ``sequence`` while the form's child table
showed them in row order, so reordering rows on the form changed nothing.
Renumbers each page's rows (``idx``) in the order the dashboard showed them -
``sequence``, then row - and drops the field from the stored definition and
the table.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-13
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from grunt.metadata.compiler import get_table_name

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_DOCTYPE = "PageWidget"
_FIELD = "sequence"


def _table(conn: sa.Connection, tables: set[str]) -> str:
    """The table from the stored definition, else the default name."""
    if _META in tables:
        meta = sa.table(_META, sa.column("name"), sa.column("table_name"))
        stored = conn.execute(
            sa.select(meta.c.table_name).where(meta.c.name == _DOCTYPE)
        ).scalar()
        if stored:
            return stored
    return get_table_name("site", _DOCTYPE)


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    table = _table(conn, tables)
    if table in tables and _FIELD in {c["name"] for c in sa.inspect(conn).get_columns(table)}:
        t = sa.table(
            table,
            sa.column("name"),
            sa.column("parent_name"),
            sa.column("idx"),
            sa.column(_FIELD),
        )
        rows = conn.execute(
            sa.select(t.c.name, t.c.parent_name).order_by(
                t.c.parent_name, sa.func.coalesce(t.c[_FIELD], 0), t.c.idx
            )
        ).all()
        position: dict[str, int] = {}
        for name, parent in rows:
            idx = position.get(parent, 0)
            position[parent] = idx + 1
            conn.execute(sa.update(t).where(t.c.name == name).values(idx=idx))
        with op.batch_alter_table(table) as batch:
            batch.drop_column(_FIELD)

    if _META in tables:
        meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON()))
        raw = conn.execute(
            sa.select(meta.c.definition).where(meta.c.name == _DOCTYPE)
        ).scalar()
        data = json.loads(raw) if isinstance(raw, str) else raw
        if data:
            fields = data.get("fields") or []
            kept = [f for f in fields if f.get("fieldname") != _FIELD]
            if len(kept) != len(fields):
                data["fields"] = kept
                conn.execute(
                    sa.update(meta).where(meta.c.name == _DOCTYPE).values(definition=data)
                )


def downgrade() -> None:
    pass
