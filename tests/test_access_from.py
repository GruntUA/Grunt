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


@pytest.mark.asyncio
async def test_core_doctype_stored_with_old_key_keeps_customisations(ctx, db_session):
    """Before 0027 a stored core definition still names the old key: loading it
    must not fall back to the JSON (that drops Studio changes) - the key is a
    core-synced attribute, the JSON's access_from replaces it."""
    from sqlalchemy import update

    from grunt.metadata import store
    from grunt.metadata.doctype import DocField
    from grunt.metadata.registry import doctype_registry

    source = [["ref_doctype", "ref_name"]]
    core = DocType(
        name="AfCoreNote",
        label="AfCoreNote",
        module="grunt",
        app="grunt",
        access_from=source,
        fields=[
            DocField(fieldname="ref_doctype", fieldtype="Link", options="DocType"),
            DocField(fieldname="ref_name", fieldtype="Data"),
        ],
    )
    await doctype_registry._inject_core(core, db_session, sync_db=True)
    stored = doctype_registry._doctypes["AfCoreNote"]
    stored.fields.append(DocField(fieldname="local_note", fieldtype="Data"))  # added in Studio
    await store.update_doctype(db_session, stored)

    old = dict(await store.get_definition(db_session, "AfCoreNote") or {})
    old["inherit_permission_from"] = old.pop("access_from")
    table = store.meta_table()
    await db_session.execute(
        update(table).where(table.c.name == "AfCoreNote").values(definition=old)
    )

    await doctype_registry._inject_core(core, db_session, sync_db=True)
    loaded = doctype_registry._doctypes["AfCoreNote"]
    assert "local_note" in [f.fieldname for f in loaded.fields]
    assert loaded.access_from == source


@pytest.mark.asyncio
async def test_link_source_to_removed_doctype_falls_back_to_role_rules():
    from grunt.metadata.doctype import DocField
    from grunt.permissions.query import _followed
    from grunt.query.nodes import FALSE, TRUE

    dt = DocType(
        name="AfFile",
        label="AfFile",
        module="core",
        fields=[DocField(fieldname="folder", fieldtype="Link", options="AfGoneFolder")],
    )
    assert await _followed("u@example.com", dt, (None, "folder"), []) == (TRUE, FALSE)
