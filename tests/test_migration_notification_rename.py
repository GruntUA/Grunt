"""Migration 0022: ``Notification`` -> ``NotificationLog``, then
``NotificationRule`` -> ``Notification`` (``grunt.db.rename_doctype``)."""

import importlib
import json
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

migration = importlib.import_module("grunt.db.migrations.versions.0022_notification_rename")

_BELL = {
    "name": "Notification",
    "table_name": "grunt_notification",
    "fields": [
        {"fieldname": "user", "fieldtype": "Data"},
        {"fieldname": "ref_doctype", "fieldtype": "Data"},
        {"fieldname": "notification_rule", "fieldtype": "Link", "options": "NotificationRule"},
    ],
    "indexes": [["notification_rule", "ref_doctype"]],
}
_RULE = {
    "name": "NotificationRule",
    "table_name": "grunt_notification_rule",
    "fields": [{"fieldname": "ref_doctype", "fieldtype": "Link", "options": "DocType"}],
}
_ACTIVITY = {
    "name": "ActivityLog",
    "table_name": "grunt_log_activity",
    "fields": [{"fieldname": "ref_doctype", "fieldtype": "Link", "options": "DocType"}],
}


def _setup(conn: sa.Connection) -> None:
    conn.execute(
        sa.text(
            "CREATE TABLE grunt_metadata_doc_type "
            "(name VARCHAR PRIMARY KEY, table_name VARCHAR, definition JSON)"
        )
    )
    for d in (_BELL, _RULE, _ACTIVITY):
        conn.execute(
            sa.text("INSERT INTO grunt_metadata_doc_type VALUES (:n, :t, :d)"),
            {"n": d["name"], "t": d["table_name"], "d": json.dumps(d)},
        )
    conn.execute(
        sa.text(
            "CREATE TABLE grunt_notification (name VARCHAR PRIMARY KEY, "
            "user VARCHAR, ref_doctype VARCHAR, notification_rule VARCHAR)"
        )
    )
    conn.execute(sa.text("CREATE INDEX ix_grunt_notification_user ON grunt_notification (user)"))
    conn.execute(sa.text("INSERT INTO grunt_notification VALUES ('n1', 'a@x', 'Task', 'r1')"))
    conn.execute(
        sa.text(
            "CREATE TABLE grunt_notification_rule (name VARCHAR PRIMARY KEY, ref_doctype VARCHAR)"
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX ix_grunt_notification_rule_ref_doctype "
            "ON grunt_notification_rule (ref_doctype)"
        )
    )
    conn.execute(sa.text("INSERT INTO grunt_notification_rule VALUES ('r1', 'Task')"))
    conn.execute(
        sa.text("CREATE TABLE grunt_log_activity (name VARCHAR PRIMARY KEY, ref_doctype VARCHAR)")
    )
    conn.execute(
        sa.text(
            "INSERT INTO grunt_log_activity VALUES "
            "('a1', 'NotificationRule'), ('a2', 'Notification'), ('a3', 'Task')"
        )
    )
    # A legacy table no definition describes: its *_doctype column is updated too.
    conn.execute(
        sa.text("CREATE TABLE legacy_tag (name VARCHAR PRIMARY KEY, reference_doctype VARCHAR)")
    )
    conn.execute(sa.text("INSERT INTO legacy_tag VALUES ('t1', 'NotificationRule')"))


def _definition(conn: sa.Connection, name: str) -> dict | None:
    row = conn.execute(
        sa.text("SELECT definition FROM grunt_metadata_doc_type WHERE name = :n"), {"n": name}
    ).first()
    return json.loads(row[0]) if row else None


def test_swaps_names_tables_and_references(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        _setup(conn)
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

        inspector = sa.inspect(conn)
        tables = set(inspector.get_table_names())
        assert "grunt_notification_rule" not in tables
        assert {"grunt_notification", "grunt_notification_log"} <= tables

        # The bell's rows moved with their table; the field is renamed.
        bell = conn.execute(sa.text("SELECT name, notification FROM grunt_notification_log")).all()
        assert bell == [("n1", "r1")]
        # The rules are under the freed name.
        rules = conn.execute(sa.text("SELECT name FROM grunt_notification")).all()
        assert rules == [("r1",)]
        # Old ix_ indexes are gone - DocType sync recreates them under the new names.
        assert not inspector.get_indexes("grunt_notification")
        assert not inspector.get_indexes("grunt_notification_log")

        log = _definition(conn, "NotificationLog")
        assert log is not None
        assert log["table_name"] == "grunt_notification_log"
        link = next(f for f in log["fields"] if f["fieldname"] == "notification")
        assert link["options"] == "Notification"
        assert log["indexes"] == [["notification", "ref_doctype"]]

        rule = _definition(conn, "Notification")
        assert rule is not None
        assert rule["name"] == "Notification"
        assert rule["table_name"] == "grunt_notification"
        assert _definition(conn, "NotificationRule") is None

        activity = dict(
            conn.execute(sa.text("SELECT name, ref_doctype FROM grunt_log_activity")).all()
        )
        assert activity == {"a1": "Notification", "a2": "NotificationLog", "a3": "Task"}
        legacy = conn.execute(sa.text("SELECT reference_doctype FROM legacy_tag")).scalar()
        assert legacy == "Notification"


def test_noop_when_already_renamed(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        _setup(conn)
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()  # a second run finds nothing left to rename
        assert _definition(conn, "NotificationRule") is None
        assert _definition(conn, "NotificationLog") is not None


def test_resumes_after_table_renamed_but_column_not(tmp_path: Path):
    """MySQL commits each DDL statement: a run that stopped after renaming the
    table is retried with the table already renamed and the column not."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        _setup(conn)
        conn.execute(sa.text("DROP INDEX ix_grunt_notification_user"))
        conn.execute(sa.text("ALTER TABLE grunt_notification RENAME TO grunt_notification_log"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

        columns = {c["name"] for c in sa.inspect(conn).get_columns("grunt_notification_log")}
        assert "notification" in columns
        assert "notification_rule" not in columns
        bell = conn.execute(sa.text("SELECT name, notification FROM grunt_notification_log")).all()
        assert bell == [("n1", "r1")]
        assert conn.execute(sa.text("SELECT name FROM grunt_notification")).all() == [("r1",)]
