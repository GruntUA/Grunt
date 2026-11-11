"""Permission rows grant a list of ``actions`` instead of one flag per action.

``{"role": "X", "read": true, "write": true}`` becomes
``{"role": "X", "actions": ["read", "write"]}`` in every stored DocType
definition - its ``permissions`` and ``permissions_base`` (what the bundled
JSON said, so an uncustomised core DocType keeps following its JSON - which
grants System Manager the new ones). Otherwise the new actions (``export``,
``import``, ``print``, ``share``) are granted to nobody here: who may take data
out is configured anew.

The stored DocPermission definition loses the flag fields: a core DocType's
stored fields that the JSON no longer has are kept as local customisations.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-11
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_ORDER = (
    "read",
    "select",
    "write",
    "create",
    "delete",
    "export",
    "import",
    "print",
    "share",
    "report",
)
_FLAGS = ("read", "select", "write", "create", "delete", "report")
# DocPermission's own form: the flag fields it had before ``actions``.
_GONE_FIELDS = {"DocPermission": set(_FLAGS)}


def _convert(row: dict) -> bool:
    if not any(flag in row for flag in _FLAGS):
        return False
    actions = set(row.get("actions") or [])
    for flag in _FLAGS:
        value = row.pop(flag, False)
        if value is True or value == 1:
            actions.add(flag)
    row["actions"] = [a for a in _ORDER if a in actions]
    return True


def _clean(name: str, data: dict) -> bool:
    changed = False
    for key in ("permissions", "permissions_base"):
        for row in data.get(key) or []:
            if isinstance(row, dict):
                changed = _convert(row) or changed
    gone = _GONE_FIELDS.get(name)
    if gone:
        fields = data.get("fields") or []
        kept = [f for f in fields if f.get("fieldname") not in gone]
        if len(kept) != len(fields):
            data["fields"] = kept
            changed = True
    return changed


def upgrade() -> None:
    conn = op.get_bind()
    if _META not in set(sa.inspect(conn).get_table_names()):
        return
    meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON))
    for name, definition in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
        data = json.loads(definition) if isinstance(definition, str) else dict(definition or {})
        if _clean(name, data):
            conn.execute(sa.update(meta).where(meta.c.name == name).values(definition=data))


def downgrade() -> None:
    pass
