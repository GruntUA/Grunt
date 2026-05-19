"""Strip legacy app-routing fields from the Page DocType metadata.

The Page DocType was previously used for frontend app-page registration
(fields: route, title, component, app). It was repurposed as the unified
dashboard/workspace page (fields: label, description, is_published, roles,
widgets). The _inject_core merge kept the old required fields, making it
impossible to create a Page through the form.

This migration replaces the stored metadata with only the correct fields.

Revision ID: 0007_fix_page_metadata
Revises: 0006_add_home_page_to_workspace
Create Date: 2026-05-11
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0007_fix_page_metadata"
down_revision = "0006_add_home_page_to_workspace"
branch_labels = None
depends_on = None

_KEEP_FIELDS = {"label", "description", "is_published", "roles", "widgets"}


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT data FROM grunt_meta_doctype WHERE name = 'Page'"))
    row = result.fetchone()
    if row is None:
        return

    raw = row[0]
    data: dict = json.loads(raw) if isinstance(raw, str) else dict(raw)
    data["fields"] = [f for f in data.get("fields", []) if f.get("fieldname") in _KEEP_FIELDS]

    conn.execute(
        sa.text("UPDATE grunt_meta_doctype SET data = :data WHERE name = 'Page'"),
        {"data": json.dumps(data)},
    )


def downgrade() -> None:
    # Cannot restore the legacy merged fields — treat as irreversible.
    pass
