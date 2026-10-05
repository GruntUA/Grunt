"""Store ``SystemSettings.language`` as a short UI-language code.

The field used to be a static Select of locale tags (``uk-UA`` / ``en-US``);
it now draws its options from the UI languages (``grunt.i18n.language`` -
``uk``, ``en``, …, whatever has a translation catalog), the same codes
``User.language`` stores.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TABLE = "grunt_site_system_settings"
_COLUMN = "language"
_TAGS = {"uk-UA": "uk", "en-US": "en"}


def _rewrite(mapping: dict[str, str]) -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_TABLE)}:
        return
    tbl = sa.table(_TABLE, sa.column(_COLUMN))
    for old, new in mapping.items():
        conn.execute(sa.update(tbl).where(tbl.c[_COLUMN] == old).values({_COLUMN: new}))


def upgrade() -> None:
    _rewrite(_TAGS)


def downgrade() -> None:
    _rewrite({short: tag for tag, short in _TAGS.items()})
