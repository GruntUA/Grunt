"""Move DocType definitions from ``grunt_meta_doctype`` into the DocType table.

DocType definitions used to live in a hand-declared ``grunt_meta_doctype``
table (JSON ``data``), with ``grunt_metadata_doc_type`` copying some of their
properties into columns for the DocType list. The DocType table now holds
both: the definition in its JSON ``definition`` column and its scalar
properties in columns, so ``grunt_meta_doctype`` goes.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_OLD = "grunt_meta_doctype"
_NEW = "grunt_metadata_doc_type"
_SYSTEM_COLUMNS = {"name", "owner", "created_at", "modified_at", "modified_by", "definition"}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if _OLD not in tables:
        return

    if _NEW not in tables:
        op.create_table(
            _NEW,
            sa.Column("name", sa.String(255), primary_key=True),
            sa.Column("owner", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("modified_at", sa.DateTime()),
            sa.Column("modified_by", sa.String(255)),
        )
    if "definition" not in {c["name"] for c in sa.inspect(conn).get_columns(_NEW)}:
        op.add_column(_NEW, sa.Column("definition", sa.JSON(), nullable=True))

    old = sa.table(
        _OLD,
        sa.column("name"),
        sa.column("data"),
        sa.column("created_at", sa.DateTime()),
        sa.column("modified_at", sa.DateTime()),
    )
    new = sa.Table(_NEW, sa.MetaData(), autoload_with=conn)
    scalar_columns = [c.name for c in new.columns if c.name not in _SYSTEM_COLUMNS]
    existing = {row[0] for row in conn.execute(sa.select(new.c.name))}

    names: set[str] = set()
    for name, raw, created_at, modified_at in conn.execute(
        sa.select(old.c.name, old.c.data, old.c.created_at, old.c.modified_at)
    ).all():
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not data:
            continue
        names.add(name)
        values = {col: data[col] for col in scalar_columns if col in data}
        values["definition"] = data
        values["modified_at"] = modified_at or datetime.now(UTC)
        if name in existing:
            conn.execute(sa.update(new).where(new.c.name == name).values(**values))
        else:
            conn.execute(
                sa.insert(new).values(
                    name=name,
                    owner="system",
                    created_at=created_at or values["modified_at"],
                    modified_by="system",
                    **values,
                )
            )

    stale = existing - names
    if stale:
        conn.execute(sa.delete(new).where(new.c.name.in_(stale)))

    op.drop_table(_OLD)


def downgrade() -> None:
    pass
