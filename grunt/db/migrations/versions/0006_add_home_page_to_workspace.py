"""Add home_page column to grunt_workspace (AppMenu).

Revision ID: 0006_add_home_page_to_workspace
Revises: 0005_rename_dashboard_to_page
Create Date: 2026-05-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_add_home_page_to_workspace"
down_revision = "0005_rename_dashboard_to_page"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("grunt_workspace")]
    if "home_page" not in columns:
        op.add_column(
            "grunt_workspace",
            sa.Column("home_page", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("grunt_workspace")]
    if "home_page" in columns:
        op.drop_column("grunt_workspace", "home_page")
