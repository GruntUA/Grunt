"""``EmailUnsubscribe`` becomes ``NotificationPreference`` (FRAPPE_GAP #18).

An unsubscribe row turned off one rule's letters (or all of them); a
preference turns off a rule (or all) in one channel or in every one - set in
the profile, from the bell or by the unsubscribe link. The table is renamed
and gains ``channel``; the rows it had were about letters, so they get
``channel = 'email'``.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

from grunt.db.rename_doctype import rename_doctype

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_TABLE = "grunt_notification_preference"


def upgrade() -> None:
    conn = op.get_bind()
    # EmailUnsubscribe sat on the default table of its module (no table_name).
    rename_doctype(
        conn,
        "EmailUnsubscribe",
        "NotificationPreference",
        new_table=_TABLE,
        old_table="grunt_email_email_unsubscribe",
    )
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return
    if "channel" not in {c["name"] for c in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column("channel", sa.String(255), nullable=True))
    # Not only right after ADD COLUMN: on MySQL it commits by itself, and a rerun
    # after a failed UPDATE would find the column and leave the rows NULL - which
    # reads as "every channel". Until 0029 is stamped a NULL here can only be an
    # old unsubscribe, i.e. a letter.
    table = sa.table(_TABLE, sa.column("channel"))
    conn.execute(sa.update(table).where(table.c.channel.is_(None)).values(channel="email"))


def downgrade() -> None:
    # Not reversible - restore the backup taken before the upgrade (grunt db restore).
    raise NotImplementedError("revision 0029 cannot be downgraded: restore a backup")
