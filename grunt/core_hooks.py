"""Core framework hooks — "app zero".

Loaded by :func:`grunt.apps.load_core` at :mod:`grunt.main` import, through
the same :data:`~grunt.apps.consumers.HOOK_CONSUMERS` path as any external
app's ``hooks.py``. Everything the framework itself needs wired on every site
lives here — declared, not imperatively registered in ``main.py``.
"""

from __future__ import annotations

doc_events: dict[str, dict[str, list[str]]] = {
    # Never hand a stored SMTP password back to a non-superadmin reader.
    "EmailAccount": {
        "after_read": ["grunt.email.hooks.mask_smtp_password"],
    },
    # Keep the notification-rule index (grunt.events "notification_rules"
    # stage) fresh.
    "NotificationRule": {
        "after_save": ["grunt.notification.rule_index.invalidate_on_change"],
        "after_delete": ["grunt.notification.rule_index.invalidate_on_change"],
    },
    # A new ToDo is an assignment — notify the person it lands on.
    "ToDo": {
        "after_insert": ["grunt.tasks.doctypes.ToDo.to_do.notify_assignee"],
    },
    # Log every document lifecycle event to ActivityLog.
    "*": {
        "after_insert": ["grunt.activity.log_activity"],
        # Snapshot the doc first (restorable trash bin), then log the delete.
        "after_delete": [
            "grunt.activity.trash.snapshot_deleted_document",
            "grunt.activity.log_activity",
        ],
        # Record per-user "seen" state / ViewLog for DocTypes that opt in via
        # track_seen / track_views (no-op for everything else).
        "after_read": ["grunt.activity.record_view"],
    },
}
