"""Core framework hooks - "app zero".

Loaded by :func:`grunt.apps.load_core` at :mod:`grunt.main` import, through
the same :data:`~grunt.apps.consumers.HOOK_CONSUMERS` path as any external
app's ``hooks.py``. Everything the framework itself needs wired on every site
lives here - declared, not imperatively registered in ``main.py``.
"""

doc_events: dict[str, dict[str, list[str]]] = {
    # Never hand a stored SMTP password back to a reader without System Manager.
    "EmailAccount": {
        "after_read": ["grunt.email.hooks.mask_smtp_password"],
    },
    # Cloud storage credentials never leave the server (grunt.storage.cloud).
    "StorageRemote": {
        "after_read": ["grunt.storage.cloud.mask_secrets"],
    },
    # OAuth client secrets and tokens never leave the server (grunt.integrations.oauth).
    "ConnectedApp": {
        "after_read": ["grunt.integrations.oauth.mask_secrets"],
    },
    "OAuthToken": {
        "after_read": ["grunt.integrations.oauth.mask_secrets"],
    },
    # Keep the notification-rule index (grunt.events "notification_rules"
    # stage) fresh.
    "Notification": {
        "after_save": ["grunt.notification.rule_index.invalidate_on_change"],
        "after_delete": ["grunt.notification.rule_index.invalidate_on_change"],
    },
    # Keep the i18n request-language negotiator in sync with active languages.
    "Language": {
        "after_save": ["grunt.i18n.hooks.refresh_supported_languages"],
        "after_delete": ["grunt.i18n.hooks.refresh_supported_languages"],
    },
    # Keep the milestone tracker cache (grunt.activity.milestones) fresh.
    "MilestoneTracker": {
        "after_delete": ["grunt.activity.milestones.invalidate"],
    },
    # Keep the SLA policy cache (grunt.notification.sla) fresh.
    "ServiceLevel": {
        "after_save": ["grunt.notification.sla.invalidate"],
        "after_delete": ["grunt.notification.sla.invalidate"],
    },
    # A group's id is its name (autoname field:group_name): a rename renames both.
    "UserGroup": {
        "after_rename": ["grunt.permissions.groups.rename_group"],
    },
    # Tell a document's followers (DocFollow) about new comments on it.
    # Auto-follow (User.follow_*): who comments / is assigned / gets a share.
    "Comment": {
        "after_insert": [
            "grunt.activity.follow.notify_followers_of_comment",
            "grunt.activity.follow.follow_commented",
        ],
    },
    "ToDo": {
        "after_insert": ["grunt.activity.follow.follow_assigned"],
        "after_save": ["grunt.activity.follow.follow_assigned"],
    },
    "SharedWith": {
        "after_insert": ["grunt.activity.follow.follow_shared"],
    },
    # ToDo assignment notifications live in its controller
    # (grunt.tasks.doctypes.ToDo.to_do.ToDo) - create / reassign / complete.
    # Log every document lifecycle event to ActivityLog.
    "*": {
        "after_insert": [
            "grunt.activity.log_activity",
            # The author follows it (User.follow_created).
            "grunt.activity.follow.follow_created",
        ],
        # Standard records (DocType.standard_records) -> JSON files in their app.
        "after_save": [
            "grunt.standard_records.sync_files",
            # Start / move / stop SLA clocks (no-op without a ServiceLevel).
            "grunt.notification.sla.on_document_saved",
            # Time-in-status history (no-op without a MilestoneTracker).
            "grunt.activity.milestones.on_document_saved",
            # Realtime: the open form and its timeline refresh themselves.
            "grunt.activity.live.announce_change",
        ],
        "after_rename": ["grunt.standard_records.sync_files"],
        # Snapshot the doc first (restorable trash bin), then log the delete.
        "after_delete": [
            "grunt.activity.trash.snapshot_deleted_document",
            "grunt.activity.log_activity",
            "grunt.activity.follow.drop_follows",
            "grunt.activity.likes.drop_likes",
            "grunt.activity.reactions.drop_reactions",
            "grunt.standard_records.sync_files",
            "grunt.notification.sla.on_document_deleted",
            "grunt.activity.milestones.on_document_deleted",
            "grunt.activity.live.announce_change",
        ],
        # Record per-user "seen" state / ViewLog for DocTypes that opt in via
        # track_seen / track_views (no-op for everything else).
        "after_read": ["grunt.activity.record_view"],
    },
}

# Built-in sign-in methods (grunt.auth.providers), imported on first use.
# An app adds its own provider class the same way; a later one replaces a name.
auth_providers: list[str] = [
    "grunt.auth.providers.webauthn.WebAuthnProvider",
    "grunt.auth.providers.oauth.GoogleProvider",
    "grunt.auth.providers.oauth.MicrosoftProvider",
    "grunt.auth.providers.email_link.EmailLoginProvider",
]

# The property list at the top of the document sidebar (grunt.document.sidebar).
# An app adds rows to it with placement="properties", or replaces one by name.
sidebar_sections: list[dict] = [
    {
        "name": "status",
        "method": "grunt.document.sidebar.status_rows",
        "placement": "properties",
        "order": 0,
    },
    {
        "name": "id",
        "method": "grunt.document.sidebar.id_row",
        "placement": "properties",
        "order": 10,
    },
    {
        # Service levels (SLA) of the document: the clock and the deadline.
        "name": "service_levels",
        "method": "grunt.notification.sla.sidebar_rows",
        "placement": "properties",
        "order": 5,
    },
    {
        "name": "web_page",
        "method": "grunt.document.sidebar.web_page_row",
        "placement": "properties",
        "order": 20,
    },
]
