"""Drop ``DocType.list_tree_field`` (the tree panel beside a list).

File browses its folders in the Explorer view, so the list panel went from the
framework. The stored definitions forget it: the DocType DocType loses the
field (stored fields the JSON no longer has are kept - see 0005) and every
DocType loses the property; the column goes too.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-16
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_GONE = "list_tree_field"
_GONE_FIELDS = (_GONE, "col_lv_2")


def upgrade() -> None:
    conn = op.get_bind()
    if _META not in sa.inspect(conn).get_table_names():
        return

    meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON()))
    for name, raw in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not data:
            continue
        changed = _GONE in data
        data.pop(_GONE, None)
        if name == "DocType":
            fields = data.get("fields") or []
            kept = [f for f in fields if f.get("fieldname") not in _GONE_FIELDS]
            if len(kept) != len(fields):
                data["fields"] = kept
                changed = True
        if changed:
            conn.execute(sa.update(meta).where(meta.c.name == name).values(definition=data))

    if _GONE in {c["name"] for c in sa.inspect(conn).get_columns(_META)}:
        with op.batch_alter_table(_META) as batch:
            batch.drop_column(_GONE)


def downgrade() -> None:
    pass
