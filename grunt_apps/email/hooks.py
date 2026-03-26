from __future__ import annotations

# Scheduler events for Email Engine
scheduler_events = {
    # Every minute - process the outgoing queue
    "all": [
        "backend.grunt.core.email.tasks.process_email_queue"
    ],
    # Every 10 minutes - pull from IMAP accounts
    "cron": [
        {
            "handler": "backend.grunt.core.email.tasks.pull_from_accounts",
            "expression": "*/10 * * * *"
        }
    ]
}

# Documentation for developers
# Apps can register to "inbound_email" hook to handle incoming mail.
# Example in another app's hooks.py:
#
# doc_events = {
#     "inbound_email": ["my_app.logic.handle_new_ticket"]
# }
