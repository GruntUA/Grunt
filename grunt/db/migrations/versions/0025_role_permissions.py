"""Roles hold permissions (``Role.permissions``); System Manager gets ``*``.

Code now asks for a permission (``has_perm``, ``@whitelist(perm=...)``)
instead of the role name "System Manager" - so that role must hold every
permission, or its users would lose the admin pages on upgrade.

The column is added when the DocType sync hasn't run yet.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-13
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

_ROLES = "grunt_auth_role"
_ADMIN = "System Manager"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _ROLES not in set(inspector.get_table_names()):
        return  # a fresh site: the role is created with "*" (ensure_system_manager)
    columns = {c["name"] for c in inspector.get_columns(_ROLES)}
    if "permissions" not in columns:
        op.add_column(_ROLES, sa.Column("permissions", sa.JSON()))
    roles = sa.table(_ROLES, sa.column("name"), sa.column("permissions", sa.JSON()))
    current = conn.execute(sa.select(roles.c.permissions).where(roles.c.name == _ADMIN)).first()
    if current is None:
        return
    held = current[0]
    if isinstance(held, str):
        held = json.loads(held or "[]")
    held = list(held or [])
    if "*" not in held:
        conn.execute(roles.update().where(roles.c.name == _ADMIN).values(permissions=["*", *held]))


def downgrade() -> None:
    pass
