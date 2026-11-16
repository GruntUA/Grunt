"""Migration 0026: User Permissions -> scoped role assignments."""

import importlib
import json
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

migration = importlib.import_module("grunt.db.migrations.versions.0026_user_permissions_to_scopes")

DOCTYPES = {
    # A moderator's publications and the section tree (mlt_portal).
    "Page": {
        "fields": [{"fieldname": "section", "fieldtype": "Link", "options": "Section"}],
        "permissions": [{"role": "Moderator"}, {"role": "Admin"}],
    },
    "Section": {
        "fields": [
            {
                "fieldname": "parent_section",
                "fieldtype": "Link",
                "options": "Section",
                "ignore_user_permissions": True,
            }
        ],
        "permissions": [{"role": "Moderator"}],
    },
    # A clerk's letters (letter) - and an executor's, by the All rule.
    "Letter": {
        "fields": [{"fieldname": "department", "fieldtype": "Link", "options": "Department"}],
        "permissions": [{"role": "Clerk"}, {"role": "All"}],
    },
    "Asset": {"fields": [], "permissions": [{"role": "Storekeeper"}]},
}


def _setup(conn: sa.Connection) -> None:
    conn.execute(sa.text("CREATE TABLE grunt_metadata_doc_type (name VARCHAR, definition JSON)"))
    for name, definition in DOCTYPES.items():
        conn.execute(
            sa.text("INSERT INTO grunt_metadata_doc_type VALUES (:n, :d)"),
            {"n": name, "d": json.dumps(definition)},
        )
    conn.execute(sa.text("CREATE TABLE grunt_auth_role (name VARCHAR, permissions JSON)"))
    conn.execute(sa.text("""INSERT INTO grunt_auth_role VALUES ('Admin', '["*"]')"""))
    conn.execute(
        sa.text(
            "CREATE TABLE grunt_auth_user_role (name VARCHAR PRIMARY KEY, owner VARCHAR, "
            "created_at DATETIME, modified_at DATETIME, modified_by VARCHAR, "
            "role_name VARCHAR, parent_name VARCHAR, parent_doctype VARCHAR, "
            "parent_field VARCHAR, idx INTEGER)"
        )
    )
    for i, (user, role) in enumerate(
        [
            ("mod", "Moderator"),
            ("mod", "Storekeeper"),
            ("clerk", "Clerk"),
            ("boss", "Admin"),
            ("executor", "Storekeeper"),
        ],
        start=1,
    ):
        conn.execute(
            sa.text(
                "INSERT INTO grunt_auth_user_role (name, role_name, parent_name, "
                "parent_doctype, parent_field, idx) VALUES (:n, :r, :u, 'User', 'roles', :i)"
            ),
            {"n": f"r{i}", "r": role, "u": user, "i": i},
        )
    conn.execute(
        sa.text(
            "CREATE TABLE grunt_permissions_user_permission (name VARCHAR PRIMARY KEY, "
            "for_user VARCHAR, allow VARCHAR, for_value VARCHAR, "
            "apply_to_all_doctypes BOOLEAN, applicable_for VARCHAR)"
        )
    )
    for name, user, allow, value, everywhere, applicable in [
        ("u1", "mod", "Section", "news", 0, "Page"),
        ("u2", "mod", "Section", "news", 0, "Section"),
        ("u3", "mod", "Section", "press", 0, "Page"),
        ("u4", "clerk", "Department", "IT", 1, None),
        ("u5", "boss", "Section", "news", 0, "Page"),  # "*" isn't scoped
        ("u6", "executor", "Department", "IT", 0, "Letter"),  # only the All rule
    ]:
        conn.execute(
            sa.text(
                "INSERT INTO grunt_permissions_user_permission VALUES (:n, :u, :a, :v, :e, :p)"
            ),
            {"n": name, "u": user, "a": allow, "v": value, "e": everywhere, "p": applicable},
        )


def test_user_permissions_become_scopes(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        _setup(conn)
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()  # nothing left to move

        assignments = conn.execute(
            sa.text(
                "SELECT parent_name, role_name, scope_doctype, scope_value "
                "FROM grunt_auth_user_role ORDER BY parent_name, role_name, scope_value"
            )
        ).all()
        left = conn.execute(
            sa.text("SELECT name FROM grunt_permissions_user_permission ORDER BY name")
        ).all()

    assert [tuple(a) for a in assignments] == [
        ("boss", "Admin", None, None),
        ("clerk", "Clerk", "Department", "IT"),
        ("executor", "Storekeeper", None, None),
        ("mod", "Moderator", "Section", "news"),
        ("mod", "Moderator", "Section", "press"),
        ("mod", "Storekeeper", None, None),  # no rule on what was restricted
    ]
    # Moved ones go; what narrowed no role ("*", only the All rule) stays, logged.
    assert [r[0] for r in left] == ["u5", "u6"]


def test_no_user_permissions_no_change(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_permissions_user_permission (name VARCHAR, for_user VARCHAR, "
                "allow VARCHAR, for_value VARCHAR, apply_to_all_doctypes BOOLEAN, "
                "applicable_for VARCHAR)"
            )
        )
        conn.execute(sa.text("CREATE TABLE grunt_auth_user_role (name VARCHAR, role_name VARCHAR)"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        columns = {c["name"] for c in sa.inspect(conn).get_columns("grunt_auth_user_role")}
    assert columns == {"name", "role_name"}  # untouched: nothing to move
