"""Rename Dashboard → Page: rename tables and update parent_doctype references.

Revision ID: 0005_rename_dashboard_to_page
Revises: 0004_rename_workspace_sidebar_to_appmenu
Create Date: 2026-05-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_rename_dashboard_to_page"
down_revision = "0004_rename_workspace_sidebar_to_appmenu"
branch_labels = None
depends_on = None

_OLD_MAIN = "grunt_reports_dashboard"
_NEW_MAIN = "grunt_site_page"
# Note: old table name has a space due to "Dashboard Widget" doctype name
_OLD_WIDGET = "grunt_reports_dashboard _widget"
_NEW_WIDGET = "grunt_site_page_widget"


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if _OLD_MAIN in tables and _NEW_MAIN not in tables:
        op.rename_table(_OLD_MAIN, _NEW_MAIN)

    # Determine widget update target based on INITIAL state to avoid stale-inspector
    # issues after op.rename_table.
    if _NEW_WIDGET in tables:
        # Already created by DocType sync before Alembic ran — just update refs.
        widget_target: str | None = _NEW_WIDGET
    elif _OLD_WIDGET in tables:
        op.rename_table(_OLD_WIDGET, _NEW_WIDGET)
        widget_target = _NEW_WIDGET
    else:
        widget_target = None

    if widget_target is not None:
        conn.execute(
            sa.text(
                f'UPDATE "{widget_target}" SET parent_doctype = :new WHERE parent_doctype = :old'
            ),
            {"new": "PageWidget", "old": "Dashboard Widget"},
        )


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if _NEW_WIDGET in tables:
        conn.execute(
            sa.text(
                f'UPDATE "{_NEW_WIDGET}" SET parent_doctype = :old WHERE parent_doctype = :new'
            ),
            {"new": "PageWidget", "old": "Dashboard Widget"},
        )
        op.rename_table(_NEW_WIDGET, _OLD_WIDGET)

    if _NEW_MAIN in tables and _OLD_MAIN not in tables:
        op.rename_table(_NEW_MAIN, _OLD_MAIN)
