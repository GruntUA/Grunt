"""``NotificationRule`` becomes ``Notification``; the bell's ``Notification``
becomes ``NotificationLog`` - as in Frappe.

The rule grows into the one place every notification is configured
(conditions, recipients, channels - NOTIFICATIONS_PLAN.md), so it takes the
plain name; a user's bell item is a log of what was delivered.

In this order (the second takes the name the first frees):

* ``Notification`` -> ``NotificationLog``: table ``grunt_notification`` ->
  ``grunt_notification_log``, field ``notification_rule`` -> ``notification``;
* ``NotificationRule`` -> ``Notification``: table ``grunt_notification_rule`` ->
  ``grunt_notification``.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op

from grunt.db.rename_doctype import rename_doctype

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if "grunt_metadata_doc_type" not in sa.inspect(conn).get_table_names():
        return
    # The swap runs once: with ``NotificationRule`` gone, ``Notification`` is
    # already the rule and must not be renamed again.
    rule = conn.execute(
        sa.text("SELECT 1 FROM grunt_metadata_doc_type WHERE name = 'NotificationRule'")
    ).first()
    if rule is None:
        return
    rename_doctype(
        conn,
        "Notification",
        "NotificationLog",
        new_table="grunt_notification_log",
        fields={"notification_rule": "notification"},
    )
    rename_doctype(conn, "NotificationRule", "Notification", new_table="grunt_notification")


def downgrade() -> None:
    # Not reversible - restore the backup taken before the upgrade (grunt db restore).
    raise NotImplementedError("revision 0022 cannot be downgraded: restore a backup")
