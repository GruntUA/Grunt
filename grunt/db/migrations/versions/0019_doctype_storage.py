"""A DocType says where its documents live: ``storage`` replaces ``is_virtual``.

``"sql"`` - the DocType's table; ``"virtual"`` - no table, the store its
controller names. Stored definitions get the new key (and lose the old one),
the DocType table its ``storage`` column - added here, before the DocType
sync, so every existing row is filled once. The old ``is_virtual`` column
stays (columns are never dropped); nothing reads it.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-07
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _META not in set(inspector.get_table_names()):
        return
    if "storage" not in {c["name"] for c in inspector.get_columns(_META)}:
        op.add_column(_META, sa.Column("storage", sa.String(100), nullable=True))

    meta = sa.table(
        _META, sa.column("name"), sa.column("definition", sa.JSON), sa.column("storage")
    )
    for name, definition in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
        data = json.loads(definition) if isinstance(definition, str) else dict(definition or {})
        storage = "virtual" if data.pop("is_virtual", False) else data.get("storage", "sql")
        data["storage"] = storage
        conn.execute(
            sa.update(meta).where(meta.c.name == name).values(definition=data, storage=storage)
        )


def downgrade() -> None:
    pass
