"""``inherit_permission_from`` is now ``access_from``.

Renames the key in every stored DocType definition - a core DocType takes it
from its JSON on load anyway, but an app's DocType keeps what is stored, and
the DocType model refuses the old key with sources in it (ignoring it would
leave comments, files, signatures to plain role rules - wider access).

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-17
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"


def _rename(old: str, new: str) -> None:
    conn = op.get_bind()
    if _META not in set(sa.inspect(conn).get_table_names()):
        return
    meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON))
    for name, definition in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
        data = json.loads(definition) if isinstance(definition, str) else dict(definition or {})
        if old not in data:
            continue
        value = data.pop(old)
        if value or new not in data:
            data[new] = value
        conn.execute(sa.update(meta).where(meta.c.name == name).values(definition=data))


def upgrade() -> None:
    _rename("inherit_permission_from", "access_from")


def downgrade() -> None:
    _rename("access_from", "inherit_permission_from")
