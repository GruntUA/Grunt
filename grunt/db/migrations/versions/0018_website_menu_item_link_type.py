"""Site menu items get «Leads to» (``link_type``) - filled from their link fields.

The form of WebsiteMenuItem (cms) now shows only the fields of the chosen kind:
a section (route), a page (a document), a link (URL) or a heading. Existing items
take the kind their filled fields imply; the column is added here, before the
DocType sync, so the backfill runs once on every existing site.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_TABLE = "grunt_cms_website_menu_item"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return
    if "link_type" not in {c["name"] for c in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column("link_type", sa.String(100), nullable=True))
    conn.execute(
        sa.text(
            f"""
            UPDATE {_TABLE} SET link_type = CASE
                WHEN route IS NOT NULL AND route != '' THEN 'Section'
                WHEN link_doctype IS NOT NULL AND link_doctype != '' THEN 'Page'
                WHEN url IS NOT NULL AND url != '' THEN 'Link'
                ELSE 'Heading'
            END
            WHERE link_type IS NULL OR link_type = ''
            """
        )
    )


def downgrade() -> None:
    pass
