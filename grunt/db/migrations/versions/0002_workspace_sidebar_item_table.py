"""Replace grunt_workspace_link with DocType-managed grunt_workspace_sidebar_item.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create new DocType-managed child table only if it doesn't exist yet
    # (DocType engine may have already created it on startup)
    if not conn.dialect.has_table(conn, "grunt_workspace_sidebar_item"):
        op.create_table(
            "grunt_workspace_sidebar_item",
            sa.Column("name", sa.String(255), primary_key=True),
            sa.Column("owner", sa.String(255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("modified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("modified_by", sa.String(255), nullable=False, server_default=""),
            sa.Column("docstatus", sa.Integer(), nullable=False, server_default="0"),
            # DocType child table required columns
            sa.Column("parent_name", sa.String(255), nullable=True, index=True),
            sa.Column(
                "parent_doctype", sa.String(255), nullable=False, server_default="WorkspaceSidebar"
            ),
            sa.Column(
                "parent_field", sa.String(255), nullable=False, server_default="sidebar_items"
            ),
            sa.Column("idx", sa.Integer(), nullable=False, server_default="0"),
            # Business fields
            sa.Column("section", sa.String(255), nullable=False, server_default=""),
            sa.Column("type", sa.String(50), nullable=False, server_default="DocType"),
            sa.Column("label", sa.String(255), nullable=False, server_default=""),
            sa.Column("icon", sa.String(50), nullable=False, server_default=""),
            sa.Column("link_to", sa.String(500), nullable=False, server_default=""),
            sa.Column("show_count", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("count_filters", sa.String(1000), nullable=False, server_default=""),
            sa.Column("show_new_btn", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("roles", sa.String(1000), nullable=False, server_default=""),
        )

    # 2. Migrate data from grunt_workspace_link → grunt_workspace_sidebar_item (if old table exists)
    if conn.dialect.has_table(conn, "grunt_workspace_link"):
        rows = conn.execute(
            sa.text(
                "SELECT id, workspace_id, section, type, label, icon, link_to, "
                "show_count, count_filters, show_new_btn, roles, sequence "
                "FROM grunt_workspace_link"
            )
        ).fetchall()

        _d = conn.dialect.name
        if _d == "sqlite":
            _insert_sql = "INSERT OR IGNORE INTO grunt_workspace_sidebar_item"
        elif _d == "mysql":
            _insert_sql = "INSERT IGNORE INTO grunt_workspace_sidebar_item"
        else:
            _insert_sql = "INSERT INTO grunt_workspace_sidebar_item ON CONFLICT (name) DO NOTHING --"

        for row in rows:
            # Use workspace_id as parent_name (it was the workspace's name/id)
            item_name = f"{row.workspace_id}-sidebar_items-{row.sequence}"
            conn.execute(
                sa.text(
                    f"{_insert_sql} "
                    "(name, parent_name, parent_doctype, parent_field, idx, "
                    " section, type, label, icon, link_to, show_count, "
                    " count_filters, show_new_btn, roles) "
                    "VALUES (:name, :parent_name, 'WorkspaceSidebar', "
                    "        'sidebar_items', :idx, :section, :type, "
                    "        :label, :icon, :link_to, :show_count, "
                    "        :count_filters, :show_new_btn, :roles)"
                ),
                {
                    "name": item_name,
                    "parent_name": row.workspace_id,
                    "idx": row.sequence,
                    "section": row.section or "",
                    "type": row.type or "DocType",
                    "label": row.label or "",
                    "icon": row.icon or "",
                    "link_to": row.link_to or "",
                    "show_count": row.show_count,
                    "count_filters": row.count_filters or "",
                    "show_new_btn": row.show_new_btn,
                    "roles": row.roles or "",
                },
            )

        op.drop_table("grunt_workspace_link")


def downgrade() -> None:
    op.create_table(
        "grunt_workspace_link",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(255), nullable=False, index=True),
        sa.Column("section", sa.String(255), nullable=False, server_default=""),
        sa.Column("type", sa.String(50), nullable=False, server_default="DocType"),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("icon", sa.String(50), nullable=False, server_default=""),
        sa.Column("link_to", sa.String(500), nullable=False, server_default=""),
        sa.Column("show_count", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("count_filters", sa.String(1000), nullable=False, server_default=""),
        sa.Column("show_new_btn", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("roles", sa.String(1000), nullable=False, server_default=""),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_table("grunt_workspace_sidebar_item")
