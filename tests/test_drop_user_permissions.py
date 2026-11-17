"""Step 4c: User Permissions are gone - role scopes replace what they did for
the UI too (the list's "Restrictions" popup, pre-filled Link fields), the field
flag is ``ignore_scope``, and migration 0028 drops the rest."""

import importlib
import json

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from grunt.metadata.field import DocField
from tests.support import make_user

migration = importlib.import_module("grunt.db.migrations.versions.0028_drop_user_permissions")

UNIT = {
    "name": "DupUnit",
    "label": "Dup Unit",
    "module": "core",
    "autoname": "field:title",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [{"role": "Clerk", "actions": ["read"]}],
}
LETTER = {
    "name": "DupLetter",
    "label": "Dup Letter",
    "module": "core",
    "fields": [
        {"fieldname": "unit", "label": "Unit", "fieldtype": "Link", "options": "DupUnit"},
        {
            "fieldname": "sender",
            "label": "Sender",
            "fieldtype": "Link",
            "options": "DupUnit",
            "ignore_user_permissions": True,  # the old name still reads
        },
    ],
    "permissions": [{"role": "Clerk", "actions": ["read", "write", "create"]}],
}


def _clerk(*units: str):
    rows = [{"role_name": "Clerk", "scope_doctype": "DupUnit", "scope_value": u} for u in units]
    return make_user("clerk@example.com", roles=rows)


@pytest.fixture
async def letters(ctx):
    from grunt.api.v1.meta import save_doctype

    for dt in (UNIT, LETTER):
        await save_doctype(doctype_data={**dt, "__is_new": True})
    for title in ("Finance", "Legal"):
        await ctx.new_doc("DupUnit", {"title": title})
    await ctx.db._session().commit()


def test_old_field_flag_reads_as_ignore_scope():
    field = DocField.model_validate(
        {"fieldname": "s", "fieldtype": "Link", "options": "X", "ignore_user_permissions": True}
    )
    assert field.ignore_scope is True


@pytest.mark.asyncio
async def test_restrictions_and_defaults_follow_role_scopes(ctx, letters, db_session, engine):
    import grunt
    from grunt.api.v1.role_scopes import get_active_scopes, get_scope_defaults

    async with grunt.context(db_session, engine, _clerk("Finance")):
        rows = await get_active_scopes("DupLetter")
        defaults = await get_scope_defaults("DupLetter")
    # The free reference (sender) neither restricts nor gets a default.
    assert [(r["fieldname"], r["value"], r["title"]) for r in rows] == [
        ("unit", "Finance", "Finance")
    ]
    assert defaults == {"unit": "Finance"}

    # Two units: still restricted, but no single default.
    async with grunt.context(db_session, engine, _clerk("Finance", "Legal")):
        assert len(await get_active_scopes("DupLetter")) == 2
        assert await get_scope_defaults("DupLetter") == {}

    # Held everywhere: nothing to show, nothing to pre-fill.
    async with grunt.context(db_session, engine, make_user("c2@example.com", roles=["Clerk"])):
        assert await get_active_scopes("DupLetter") == []
        assert await get_scope_defaults("DupLetter") == {}


def _db_with(rows: list[tuple], definitions: dict[str, dict]) -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE grunt_metadata_doc_type (name TEXT, definition JSON)"))
        for name, definition in definitions.items():
            conn.execute(
                sa.text("INSERT INTO grunt_metadata_doc_type VALUES (:n, :d)"),
                {"n": name, "d": json.dumps(definition)},
            )
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_permissions_user_permission "
                "(for_user TEXT, allow TEXT, for_value TEXT, applicable_for TEXT)"
            )
        )
        for row in rows:
            conn.execute(
                sa.text("INSERT INTO grunt_permissions_user_permission VALUES (:u, :a, :v, :f)"),
                dict(zip("uavf", row, strict=True)),
            )
    return engine


def test_migration_drops_user_permissions(caplog):
    engine = _db_with(
        [("clerk@x.com", "Department", "IT", "IncomingLetter")],
        {
            "UserPermission": {"name": "UserPermission"},
            "SystemSettings": {
                "fields": [
                    {"fieldname": "site_name"},
                    {"fieldname": "sec_user_permissions"},
                    {"fieldname": "apply_strict_user_permissions"},
                ]
            },
            "Letter": {
                "fields": [{"fieldname": "sender", "ignore_user_permissions": True}],
            },
        },
    )
    with engine.begin() as conn, caplog.at_level("WARNING", logger="alembic.0028"):
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        tables = set(sa.inspect(conn).get_table_names())
        stored = {
            name: json.loads(d) if isinstance(d, str) else d
            for name, d in conn.execute(
                sa.text("SELECT name, definition FROM grunt_metadata_doc_type")
            ).all()
        }
    assert "grunt_permissions_user_permission" not in tables
    assert "UserPermission" not in stored
    assert [f["fieldname"] for f in stored["SystemSettings"]["fields"]] == ["site_name"]
    assert stored["Letter"]["fields"] == [{"fieldname": "sender", "ignore_scope": True}]
    assert "clerk@x.com" in caplog.text and "IT" in caplog.text
