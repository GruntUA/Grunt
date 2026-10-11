"""The public site's DocTypes move from the core to the ``cms`` app.

Pages, blocks, site settings, menus and web forms are the CMS's now - the core
keeps only the website engine (www pages, web view, sitemap). Their stored
definitions change owner (``app``/``module`` ``cms``) and their tables take the
CMS's names (``grunt_cms_<doctype>``), so the data stays where the app expects it.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-11
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from grunt.utils.strings import to_snake_case

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_APP = "cms"

# DocType -> its table before the move
_MOVED = {
    "WebPage": "grunt_web_page",
    "WebPageBlock": "grunt_site_web_page_block",
    "WebsiteSettings": "grunt_site_website_settings",
    "WebsiteNavItem": "grunt_site_website_nav_item",
    "WebsiteFooterColumn": "grunt_site_website_footer_column",
    "WebsiteMenuItem": "grunt_site_website_menu_item",
    "WebForm": "grunt_web_form",
    "WebFormField": "grunt_site_web_form_field",
}


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    for doctype, old_table in _MOVED.items():
        new_table = f"grunt_{_APP}_{to_snake_case(doctype)}"
        if old_table in tables and new_table not in tables:
            op.rename_table(old_table, new_table)

    # The old CMS stub's never-used child tables.
    for table in ("grunt_CMS_footer_item", "grunt_CMS_navbar_item"):
        if table in tables:
            op.drop_table(table)

    if _META not in tables:
        return
    meta = sa.table(
        _META,
        sa.column("name"),
        sa.column("app"),
        sa.column("module"),
        sa.column("table_name"),
        sa.column("definition", sa.JSON()),
    )
    conn.execute(sa.delete(meta).where(meta.c.name.in_(["FooterItem", "NavbarItem"])))
    for name, definition in conn.execute(
        sa.select(meta.c.name, meta.c.definition).where(meta.c.name.in_(list(_MOVED)))
    ):
        data = json.loads(definition) if isinstance(definition, str) else definition
        if data:
            data.update(app=_APP, module=_APP, table_name=None)
        conn.execute(
            sa.update(meta)
            .where(meta.c.name == name)
            .values(app=_APP, module=_APP, table_name=None, definition=data)
        )


def downgrade() -> None:
    pass
