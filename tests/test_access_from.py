"""``inherit_permission_from`` -> ``access_from``: the stored definitions are
renamed by migration 0027, and the DocType model never silently drops sources
(that would leave the rows to plain role rules - wider access)."""

import importlib
import json

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from grunt.metadata.doctype import DocType

migration = importlib.import_module("grunt.db.migrations.versions.0027_access_from")

BASE = {"name": "Note", "label": "Note", "module": "core", "fields": []}


def test_old_key_with_sources_is_refused():
    with pytest.raises(ValueError, match="access_from"):
        DocType.model_validate({**BASE, "inherit_permission_from": [["ref_doctype", "ref_name"]]})


@pytest.mark.parametrize("empty", [None, []])
def test_empty_old_key_is_dropped(empty):
    dt = DocType.model_validate({**BASE, "inherit_permission_from": empty})
    assert dt.access_from is None


def test_new_key_kept():
    dt = DocType.model_validate({**BASE, "access_from": [["ref_doctype", "ref_name"], "folder"]})
    assert dt.access_from == [["ref_doctype", "ref_name"], "folder"]


def _run(engine: sa.Engine, step) -> dict[str, dict]:
    with engine.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        step()
        rows = conn.execute(sa.text("SELECT name, definition FROM grunt_metadata_doc_type"))
        return {name: json.loads(d) if isinstance(d, str) else d for name, d in rows.all()}


def test_migration_renames_stored_key_both_ways():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE grunt_metadata_doc_type (name TEXT, definition JSON)"))
        for name, definition in (
            ("ESignature", {"inherit_permission_from": [["ref_doctype", "ref_name"]]}),
            ("Plain", {"inherit_permission_from": None}),
            ("Untouched", {"label": "U"}),
        ):
            conn.execute(
                sa.text("INSERT INTO grunt_metadata_doc_type VALUES (:n, :d)"),
                {"n": name, "d": json.dumps(definition)},
            )

    up = _run(engine, migration.upgrade)
    assert up["ESignature"] == {"access_from": [["ref_doctype", "ref_name"]]}
    assert up["Plain"] == {"access_from": None}
    assert up["Untouched"] == {"label": "U"}

    down = _run(engine, migration.downgrade)
    assert down["ESignature"] == {"inherit_permission_from": [["ref_doctype", "ref_name"]]}
    assert down["Untouched"] == {"label": "U"}
