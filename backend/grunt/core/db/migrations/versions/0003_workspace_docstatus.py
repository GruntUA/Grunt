"""Add docstatus, owner, modified_by to grunt_workspace.

Revision ID: 0003_workspace_docstatus
Revises: 0002_workspace_sidebar_item_table
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_workspace_docstatus'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("grunt_workspace", sa.Column("docstatus", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("grunt_workspace", sa.Column("owner", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("grunt_workspace", sa.Column("modified_by", sa.String(length=255), nullable=False, server_default=""))


def downgrade():
    op.drop_column("grunt_workspace", "docstatus")
    op.drop_column("grunt_workspace", "owner")
    op.drop_column("grunt_workspace", "modified_by")
