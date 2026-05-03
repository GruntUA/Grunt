"""Add widgets column to grunt_workspace.

Revision ID: 0001
Revises:
Create Date: 2026-04-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("grunt_workspace")}
    if "widgets" not in existing:
        op.add_column(
            "grunt_workspace",
            sa.Column("widgets", sa.Text(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    op.drop_column("grunt_workspace", "widgets")
