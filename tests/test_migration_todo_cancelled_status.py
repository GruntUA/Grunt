"""Migration 0030: ToDo rows a rule unassigned as 'Cancel' become 'Cancelled'."""

import importlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

migration = importlib.import_module("grunt.db.migrations.versions.0030_todo_cancelled_status")


def test_cancel_becomes_cancelled():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE grunt_tasks_to_do (name TEXT, status TEXT)"))
        for name, status in (("a", "Cancel"), ("b", "Open"), ("c", "Closed"), ("d", "Cancelled")):
            conn.execute(
                sa.text("INSERT INTO grunt_tasks_to_do VALUES (:n, :s)"), {"n": name, "s": status}
            )
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        rows = dict(conn.execute(sa.text("SELECT name, status FROM grunt_tasks_to_do")).all())
    assert rows == {"a": "Cancelled", "b": "Open", "c": "Closed", "d": "Cancelled"}


def test_no_table_is_fine():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
