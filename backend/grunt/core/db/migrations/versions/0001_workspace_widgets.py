"""Add widgets column to grunt_workspace.

Revision ID: 0001
Revises:
Create Date: 2026-04-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "grunt_workspace",
        sa.Column("widgets", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("grunt_workspace", "widgets")
