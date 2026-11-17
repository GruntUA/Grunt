"""Drop User Permissions - scoped roles replace them (PERMISSIONS_PLAN, step 4c).

0026 moved every User Permission a role scope says exactly; what it left are
rows a scope would have read differently - most often narrowing a DocType's
``All`` rule as well. Those go now and are logged: their users keep what their
roles and role scopes give.

Also in every stored DocType definition:

* the DocType ``UserPermission`` and its table;
* a field flag ``ignore_user_permissions`` is now ``ignore_scope``;
* ``SystemSettings`` loses its "strict user permissions" fields (a stored core
  DocType keeps fields its JSON no longer has as local customisations).

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-17
"""

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0028")

_META = "grunt_metadata_doc_type"
_TABLE = "grunt_permissions_user_permission"
_GONE_FIELDS = {"SystemSettings": {"sec_user_permissions", "apply_strict_user_permissions"}}


def _clean(name: str, data: dict) -> bool:
    changed = False
    fields = data.get("fields") or []
    gone = _GONE_FIELDS.get(name, set())
    kept = [f for f in fields if not (isinstance(f, dict) and f.get("fieldname") in gone)]
    if len(kept) != len(fields):
        data["fields"] = fields = kept
        changed = True
    for field in fields:
        if isinstance(field, dict) and "ignore_user_permissions" in field:
            old = field.pop("ignore_user_permissions")
            if old and not field.get("ignore_scope"):
                field["ignore_scope"] = old
            changed = True
    return changed


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if _TABLE in tables:
        rows = conn.execute(
            sa.text(f"SELECT for_user, allow, for_value, applicable_for FROM {_TABLE}")
        ).all()
        for user, allow, value, applicable_for in rows:
            log.warning(
                "0028: %s - UserPermission %s=%s (%s) dropped; roles and scopes decide now",
                user,
                allow,
                value,
                applicable_for or "every DocType",
            )
        op.drop_table(_TABLE)
    if _META not in tables:
        return
    meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON))
    conn.execute(sa.delete(meta).where(meta.c.name == "UserPermission"))
    for name, definition in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
        data = json.loads(definition) if isinstance(definition, str) else dict(definition or {})
        if _clean(name, data):
            conn.execute(sa.update(meta).where(meta.c.name == name).values(definition=data))


def downgrade() -> None:
    """The rows don't come back (the DocType does, from the JSON of the code
    before 0028, with an empty table). ``ignore_scope`` is renamed back - code
    before 0028 only knows the old flag."""
    conn = op.get_bind()
    if _META not in set(sa.inspect(conn).get_table_names()):
        return
    meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON))
    for name, definition in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
        data = json.loads(definition) if isinstance(definition, str) else dict(definition or {})
        changed = False
        for field in data.get("fields") or []:
            if isinstance(field, dict) and "ignore_scope" in field:
                field["ignore_user_permissions"] = field.pop("ignore_scope")
                changed = True
        if changed:
            conn.execute(sa.update(meta).where(meta.c.name == name).values(definition=data))
