"""Drop the unused Dashboard, Dashboard Widget, DashboardChart and NumberCard DocTypes.

An app's dashboards are Pages (see ``workspace._dashboards``) - nothing read
these DocTypes any more. Drops their tables and stored definitions.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-13
"""

import json

import sqlalchemy as sa
from alembic import op

from grunt.metadata.compiler import get_table_name

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_DROPPED = ("Dashboard", "Dashboard Widget", "DashboardChart", "NumberCard")


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    targets = {get_table_name("reports", name) for name in _DROPPED}
    if _META in tables:
        meta = sa.table(
            _META,
            sa.column("name"),
            sa.column("table_name"),
            sa.column("definition", sa.JSON()),
        )
        rows = conn.execute(
            sa.select(meta.c.name, meta.c.table_name, meta.c.definition).where(
                meta.c.name.in_(_DROPPED)
            )
        ).all()
        for name, table_name, raw in rows:
            data = (json.loads(raw) if isinstance(raw, str) else raw) or {}
            targets.add(
                table_name
                or data.get("table_name")
                or get_table_name(data.get("module", "reports"), name)
            )
        conn.execute(sa.delete(meta).where(meta.c.name.in_(_DROPPED)))

    for table in sorted(targets & tables):
        op.drop_table(table)


def downgrade() -> None:
    pass
