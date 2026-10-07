"""Drop ``docstatus`` / ``is_submittable`` and child-table permissions.

Submit/Cancel never had a UI - Workflow covers document states - so the
``docstatus`` column goes from every table, ``is_submittable`` from DocType and
the ``submit``/``cancel`` flags from DocPermission. Child DocTypes take their
access from the parent document now, so their own permission rows are cleared.

A core DocType's stored fields that the JSON no longer has are kept as local
customisations (see 0005), so the stored definitions of DocType and
DocPermission forget the removed fields here too - including the layout fields
of the reorganised DocType form.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-07
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_META = "grunt_meta_doctype"
_GONE_FIELDS = {
    "DocType": {
        "is_submittable",
        "tab_fields",
        "tab_links",
        "tab_tree",
        "sec_ux",
        "sec_lifecycle",
        "sec_search",
        "col_lc_1",
        "col_lc_2",
    },
    "DocPermission": {"submit", "cancel"},
}
_GONE_PERMISSION_KEYS = ("submit", "cancel", "amend")
_GONE_COLUMNS = ("docstatus", "is_submittable")


def _clean(name: str, data: dict) -> bool:
    changed = data.pop("is_submittable", None) is not None
    gone = _GONE_FIELDS.get(name)
    if gone:
        fields = data.get("fields") or []
        kept = [f for f in fields if f.get("fieldname") not in gone]
        if len(kept) != len(fields):
            data["fields"] = kept
            changed = True
    if data.get("is_child") and data.get("permissions"):
        data["permissions"] = []
        changed = True
    for perm in data.get("permissions") or []:
        for key in _GONE_PERMISSION_KEYS:
            changed = perm.pop(key, None) is not None or changed
    return changed


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if _META in tables:
        meta = sa.table(_META, sa.column("name"), sa.column("data"))
        for name, raw in conn.execute(sa.select(meta.c.name, meta.c.data)).all():
            data = json.loads(raw) if isinstance(raw, str) else raw
            if data and _clean(name, data):
                conn.execute(
                    sa.update(meta).where(meta.c.name == name).values(data=json.dumps(data))
                )

    for table in tables:
        columns = {col["name"] for col in inspector.get_columns(table)}
        gone = [c for c in _GONE_COLUMNS if c in columns]
        if table == "grunt_metadata_doc_permission":
            gone += [c for c in ("submit", "cancel") if c in columns]
        for column in gone:
            op.drop_column(table, column)


def downgrade() -> None:
    pass
