from __future__ import annotations

# System-level hooks
doc_events = {
    "*": {
        "after_insert": ["grunt_apps.system.activity.log_activity"],
        "after_update": ["grunt_apps.system.activity.log_activity"],
        "after_delete": ["grunt_apps.system.activity.log_activity"],
    }
}
