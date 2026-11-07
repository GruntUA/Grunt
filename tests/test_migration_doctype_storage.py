"""Migration 0019: stored DocType definitions get ``storage`` in place of ``is_virtual``."""

import importlib
import json
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

migration = importlib.import_module("grunt.db.migrations.versions.0019_doctype_storage")


def test_is_virtual_becomes_storage(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_metadata_doc_type "
                "(name VARCHAR PRIMARY KEY, definition JSON, is_virtual BOOLEAN)"
            )
        )
        rows = {
            "Hook": {"name": "Hook", "is_virtual": True},
            "ToDo": {"name": "ToDo", "is_virtual": False},
            "Plain": {"name": "Plain"},
        }
        for name, definition in rows.items():
            conn.execute(
                sa.text("INSERT INTO grunt_metadata_doc_type VALUES (:n, :d, :v)"),
                {"n": name, "d": json.dumps(definition), "v": definition.get("is_virtual")},
            )

        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()

        result = {
            name: (json.loads(definition), storage)
            for name, definition, storage in conn.execute(
                sa.text("SELECT name, definition, storage FROM grunt_metadata_doc_type")
            )
        }
    engine.dispose()

    assert result["Hook"] == ({"name": "Hook", "storage": "virtual"}, "virtual")
    assert result["ToDo"] == ({"name": "ToDo", "storage": "sql"}, "sql")
    assert result["Plain"] == ({"name": "Plain", "storage": "sql"}, "sql")


def test_without_the_table_does_nothing(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()
    engine.dispose()
