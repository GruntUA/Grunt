"""Merge the ``Text`` field type into ``Data`` and ``HTMLEditor`` into ``Code``.

``Text`` was a second single-line VARCHAR beside ``Data`` (which also offers
autocomplete), ``HTMLEditor`` a ``Code`` field locked to HTML. Both columns
stay as they are; only the stored definitions change: every field of type
``Text`` becomes ``Data``, every ``HTMLEditor`` becomes ``Code`` with
``options: html``. CMS web-form rows that copy a field type are renamed too.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-22
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_WEB_FORM_FIELD = "grunt_cms_web_form_field"
_RENAMED = {"Text": ("Data", None), "HTMLEditor": ("Code", "html")}


def _rename(field: dict) -> bool:
    if field.get("fieldtype") not in _RENAMED:
        return False
    fieldtype, options = _RENAMED[field["fieldtype"]]
    field["fieldtype"] = fieldtype
    if options and not field.get("options"):
        field["options"] = options
    return True


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if _META in tables:
        meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON()))
        for name, raw in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not data:
                continue
            changed = False
            for field in data.get("fields") or []:
                changed |= isinstance(field, dict) and _rename(field)
            if changed:
                conn.execute(sa.update(meta).where(meta.c.name == name).values(definition=data))

    if _WEB_FORM_FIELD in tables:
        rows = sa.table(_WEB_FORM_FIELD, sa.column("fieldtype"))
        for old, (new, _options) in _RENAMED.items():
            conn.execute(sa.update(rows).where(rows.c.fieldtype == old).values(fieldtype=new))


def downgrade() -> None:
    pass
