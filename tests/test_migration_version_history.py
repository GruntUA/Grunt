"""Migration 0020: history past ``max_versions`` is deleted, the rest stored
without ``\\uXXXX`` escapes (SQLite)."""

import importlib
import json
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

migration = importlib.import_module("grunt.db.migrations.versions.0020_version_history_limits")


def test_prunes_per_doctype_limit_and_unescapes(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE grunt_metadata_doc_type (name VARCHAR, definition JSON)")
        )
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_doc_version (name VARCHAR PRIMARY KEY, "
                "ref_doctype VARCHAR, doc_id VARCHAR, version INTEGER, changes JSON)"
            )
        )
        for name, definition in {
            "Menu": {"name": "Menu"},  # the default, 50
            "Small": {"name": "Small", "max_versions": 2},
            "All": {"name": "All", "max_versions": 0},
        }.items():
            conn.execute(
                sa.text("INSERT INTO grunt_metadata_doc_type VALUES (:n, :d)"),
                {"n": name, "d": json.dumps(definition)},
            )
        rows = [("Menu", "m1", 60), ("Small", "s1", 5), ("All", "a1", 70), ("Menu", "m2", 3)]
        for dt, doc_id, count in rows:
            for v in range(1, count + 1):
                change = [{"field": "title", "old": None, "new": f"Привіт {v}"}]
                conn.execute(
                    sa.text("INSERT INTO grunt_doc_version VALUES (:n, :dt, :id, :v, :c)"),
                    {
                        "n": f"{dt}-{doc_id}-v{v}",
                        "dt": dt,
                        "id": doc_id,
                        "v": v,
                        "c": json.dumps(change),
                    },  # ASCII-escaped, as older rows were
                )

        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

        def versions(dt, doc_id):
            return [
                v
                for (v,) in conn.execute(
                    sa.text(
                        "SELECT version FROM grunt_doc_version "
                        "WHERE ref_doctype = :dt AND doc_id = :id ORDER BY version"
                    ),
                    {"dt": dt, "id": doc_id},
                )
            ]

        assert versions("Menu", "m1") == list(range(11, 61))
        assert versions("Small", "s1") == [4, 5]
        assert len(versions("All", "a1")) == 70
        assert versions("Menu", "m2") == [1, 2, 3]
        stored = conn.execute(
            sa.text("SELECT changes FROM grunt_doc_version WHERE name = 'Small-s1-v5'")
        ).scalar()
    engine.dispose()
    assert isinstance(stored, str)
    assert "Привіт 5" in stored and "\\u" not in stored


def test_without_the_tables_does_nothing(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()
    engine.dispose()
