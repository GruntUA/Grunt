"""Rename WorkspaceSidebar → AppMenu in parent_doctype column.

Revision ID: 0004_rename_workspace_sidebar_to_appmenu
Revises: 0003_workspace_docstatus
Create Date: 2026-05-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_rename_workspace_sidebar_to_appmenu"
down_revision = "0003_workspace_docstatus"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("grunt_workspace_sidebar_item"):
        conn.execute(
            sa.text(
                "UPDATE grunt_workspace_sidebar_item "
                "SET parent_doctype = 'AppMenu' "
                "WHERE parent_doctype = 'WorkspaceSidebar'"
            )
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("grunt_workspace_sidebar_item"):
        conn.execute(
            sa.text(
                "UPDATE grunt_workspace_sidebar_item "
                "SET parent_doctype = 'WorkspaceSidebar' "
                "WHERE parent_doctype = 'AppMenu'"
            )
        )
