"""Assignments a rule unassigned get ``status = 'Cancelled'``.

Until now the assignment rules (``unassign_condition``) wrote ``'Cancel'`` - not
one of ToDo's statuses: such an assignment dropped out of the open ones, but
read as neither closed nor cancelled. Those rows get the real status.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_TABLE = "grunt_tasks_to_do"


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in sa.inspect(conn).get_table_names():
        return
    table = sa.table(_TABLE, sa.column("status"))
    conn.execute(sa.update(table).where(table.c.status == "Cancel").values(status="Cancelled"))


def downgrade() -> None:
    # Nothing to undo: 'Cancel' was never a valid status.
    pass
