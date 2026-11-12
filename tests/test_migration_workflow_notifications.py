"""Migration 0024: ``WorkflowTransition.notify`` / ``notify_email`` -> ``on_transition`` rules."""

import importlib
import json
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

migration = importlib.import_module("grunt.db.migrations.versions.0024_workflow_notifications")


def test_transitions_become_rules(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE grunt_metadata_doc_type (name VARCHAR, definition JSON)")
        )
        conn.execute(
            sa.text("INSERT INTO grunt_metadata_doc_type VALUES ('WorkflowTransition', :d)"),
            {"d": json.dumps({"fields": [{"fieldname": "action"}, {"fieldname": "notify"},
                                         {"fieldname": "notify_email"}]})},
        )  # fmt: skip
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_metadata_workflow "
                "(name VARCHAR PRIMARY KEY, document_type VARCHAR)"
            )
        )
        conn.execute(sa.text("INSERT INTO grunt_metadata_workflow VALUES ('Page', 'Page')"))
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_metadata_workflow_transition (name VARCHAR PRIMARY KEY, "
                "parent_name VARCHAR, idx INTEGER, action VARCHAR, "
                "notify TEXT, notify_email BOOLEAN)"
            )
        )
        for idx, (action, notify, email) in enumerate(
            [
                ("Send", "next", 1),
                ("Publish", "previous, owner", 0),
                ("Send", "next", 0),  # the same action again: one rule, still mailed
                ("Edited", "next", 0),
                ("Archive", "", 0),  # nobody to notify: no rule
            ],
            start=1,
        ):
            conn.execute(
                sa.text(
                    "INSERT INTO grunt_metadata_workflow_transition VALUES "
                    "(:n, 'Page', :i, :a, :notify, :e)"
                ),
                {"n": f"t{idx}", "i": idx, "a": action, "notify": notify, "e": email},
            )
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_notification (name VARCHAR PRIMARY KEY, owner VARCHAR, "
                "created_at DATETIME, modified_at DATETIME, modified_by VARCHAR, "
                "ref_doctype VARCHAR, event VARCHAR, subject_template VARCHAR, "
                "message_template TEXT, is_enabled BOOLEAN, is_standard BOOLEAN)"
            )
        )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()  # nothing left to move

        rules = conn.execute(
            sa.text(
                "SELECT name, event, workflow_actions, subject_template FROM grunt_notification"
            )
        ).all()
        recipients = conn.execute(
            sa.text(
                "SELECT parent_name, kind FROM grunt_notification_recipient "
                "ORDER BY parent_name, idx"
            )
        ).all()
        channels = conn.execute(
            sa.text(
                "SELECT parent_name, channel FROM grunt_notification_channel "
                "ORDER BY parent_name, idx"
            )
        ).all()
        columns = {
            c["name"] for c in sa.inspect(conn).get_columns("grunt_metadata_workflow_transition")
        }
        stored = conn.execute(sa.text("SELECT definition FROM grunt_metadata_doc_type")).scalar()

    by_name = {r[0]: r for r in rules}
    assert set(by_name) == {"Page · Send / Edited", "Page · Publish"}
    assert by_name["Page · Send / Edited"][1:3] == ("on_transition", "Send\nEdited")
    assert by_name["Page · Publish"][3] == migration.SUBJECT
    assert [tuple(r) for r in recipients] == [
        ("Page · Publish", "Author"),
        ("Page · Publish", "Previous actor"),
        ("Page · Send / Edited", "Next actors"),
    ]
    assert [c for p, c in channels if p == "Page · Send / Edited"] == [
        "in_app",
        "web_push",
        "email",
    ]
    assert [c for p, c in channels if p == "Page · Publish"] == ["in_app", "web_push"]
    assert "notify" not in columns and "notify_email" not in columns
    assert [f["fieldname"] for f in json.loads(stored or "{}")["fields"]] == ["action"]
