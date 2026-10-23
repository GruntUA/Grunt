"""Drop the SystemHealthCheck and SystemHealthItem DocTypes.

«Стан системи» renders its tables as server markup (HTMLView, see
``grunt.monitoring.health.render``) - nothing uses these virtual child
DocTypes any more. They never had tables; only the stored definitions go.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_DROPPED = ("SystemHealthCheck", "SystemHealthItem")


def upgrade() -> None:
    conn = op.get_bind()
    if _META not in set(sa.inspect(conn).get_table_names()):
        return
    meta = sa.table(_META, sa.column("name"))
    conn.execute(sa.delete(meta).where(meta.c.name.in_(_DROPPED)))


def downgrade() -> None:
    pass
