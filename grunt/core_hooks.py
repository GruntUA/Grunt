"""Core framework hooks - "app zero".

Loaded by :func:`grunt.apps.load_core` at :mod:`grunt.main` import, through
the same :data:`~grunt.apps.consumers.HOOK_CONSUMERS` path as any external
app's ``hooks.py``. Everything the framework itself needs wired on every site
lives here - declared, not imperatively registered in ``main.py``.
"""

from __future__ import annotations

doc_events: dict[str, dict[str, list[str]]] = {
    # Never hand a stored SMTP password back to a reader without System Manager.
    "EmailAccount": {
        "after_read": ["grunt.email.hooks.mask_smtp_password"],
    },
    # Keep the notification-rule index (grunt.events "notification_rules"
    # stage) fresh.
    "NotificationRule": {
        "after_save": ["grunt.notification.rule_index.invalidate_on_change"],
        "after_delete": ["grunt.notification.rule_index.invalidate_on_change"],
    },
    # Keep the i18n request-language negotiator in sync with active languages.
    "Language": {
        "after_save": ["grunt.i18n.hooks.refresh_supported_languages"],
        "after_delete": ["grunt.i18n.hooks.refresh_supported_languages"],
    },
    # Keep the SLA policy cache (grunt.notification.sla) fresh.
    "ServiceLevel": {
        "after_save": ["grunt.notification.sla.invalidate"],
        "after_delete": ["grunt.notification.sla.invalidate"],
    },
    # Tell a document's followers (DocFollow) about new comments on it.
    "Comment": {
        "after_insert": ["grunt.activity.follow.notify_followers_of_comment"],
    },
    # ToDo assignment notifications live in its controller
    # (grunt.tasks.doctypes.ToDo.to_do.ToDo) - create / reassign / complete.
    # Log every document lifecycle event to ActivityLog.
    "*": {
        "after_insert": ["grunt.activity.log_activity"],
        # Standard records (DocType.standard_records) -> JSON files in their app.
        "after_save": [
            "grunt.standard_records.sync_files",
            # Start / move / stop SLA clocks (no-op without a ServiceLevel).
            "grunt.notification.sla.on_document_saved",
        ],
        "after_rename": ["grunt.standard_records.sync_files"],
        # Snapshot the doc first (restorable trash bin), then log the delete.
        "after_delete": [
            "grunt.activity.trash.snapshot_deleted_document",
            "grunt.activity.log_activity",
            "grunt.activity.follow.drop_follows",
            "grunt.activity.likes.drop_likes",
            "grunt.standard_records.sync_files",
            "grunt.notification.sla.on_document_deleted",
        ],
        # Record per-user "seen" state / ViewLog for DocTypes that opt in via
        # track_seen / track_views (no-op for everything else).
        "after_read": ["grunt.activity.record_view"],
    },
}
