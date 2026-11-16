"""Migration 0026: User Permissions -> scoped role assignments - only what a
scope says exactly, never widening access."""

import importlib
import json
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

migration = importlib.import_module("grunt.db.migrations.versions.0026_user_permissions_to_scopes")

SECTION_LINK = {"fieldname": "section", "fieldtype": "Link", "options": "Section"}
DOCTYPES = {
    # Publications and the section tree (mlt_portal).
    "Page": {"fields": [SECTION_LINK], "permissions": [{"role": "Moderator"}]},
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
    # Letters: a clerk's rule and an executor's All rule (letter).
    "Letter": {
        "fields": [{"fieldname": "department", "fieldtype": "Link", "options": "Department"}],
        "permissions": [{"role": "Clerk"}, {"role": "All"}],
    },
    # Memos: the clerk only.
    "Memo": {
        "fields": [{"fieldname": "department", "fieldtype": "Link", "options": "Department"}],
        "permissions": [{"role": "Clerk"}, {"role": "Archivist"}],
    },
    # A MultiLink is no scope field.
    "Tagged": {
        "fields": [{"fieldname": "sections", "fieldtype": "MultiLink", "options": "Section"}],
        "permissions": [{"role": "Tagger"}],
    },
    "Asset": {"fields": [], "permissions": [{"role": "Storekeeper"}]},
}

ASSIGNMENTS = [
    ("even", "Moderator"),  # the same sections on Page and Section
    ("even", "Storekeeper"),
    ("uneven", "Moderator"),  # Page: news + press, Section: news only
    ("clerk", "Clerk"),  # restricted on Memo only - but the role reaches Letter too
    ("clerk2", "Clerk"),  # Letter too - its All rule stays open
    ("boss", "Admin"),  # "*" - a user User Permissions didn't bind
    ("boss", "Moderator"),
    ("tagger", "Tagger"),
    ("archivist", "Clerk"),
    ("archivist", "Archivist"),
]

USER_PERMISSIONS = [
    ("e1", "even", "Section", "news", 0, "Page"),
    ("e2", "even", "Section", "news", 0, "Section"),
    ("u1", "uneven", "Section", "news", 0, "Page"),
    ("u2", "uneven", "Section", "press", 0, "Page"),
    ("u3", "uneven", "Section", "news", 0, "Section"),
    ("c1", "clerk", "Department", "IT", 0, "Memo"),
    ("c2", "clerk2", "Department", "IT", 1, None),
    ("b1", "boss", "Section", "news", 0, "Page"),
    ("t1", "tagger", "Section", "news", 0, "Tagged"),
    ("a1", "archivist", "Department", "IT", 0, "Memo"),
]


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
    for i, (user, role) in enumerate(ASSIGNMENTS, start=1):
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
    for row in USER_PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO grunt_permissions_user_permission VALUES (:n, :u, :a, :v, :e, :p)"
            ),
            dict(zip("nuavep", row, strict=True)),
        )
    conn.execute(
        sa.text(
            "CREATE TABLE grunt_permissions_shared_with "
            "(name VARCHAR, reference_doctype VARCHAR, reference_id VARCHAR, user VARCHAR)"
        )
    )


def _migrate(tmp_path: Path) -> tuple[dict[str, list[tuple]], list[str]]:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        _setup(conn)
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()  # nothing more to move
        rows = conn.execute(
            sa.text(
                "SELECT parent_name, role_name, scope_doctype, scope_value "
                "FROM grunt_auth_user_role ORDER BY parent_name, role_name, scope_value"
            )
        ).all()
        left = conn.execute(
            sa.text("SELECT name FROM grunt_permissions_user_permission ORDER BY name")
        ).all()
    by_user: dict[str, list[tuple]] = {}
    for user, *rest in rows:
        by_user.setdefault(user, []).append(tuple(rest))
    return by_user, [r[0] for r in left]


def test_only_exact_scopes_and_no_widening(tmp_path: Path):
    roles, left = _migrate(tmp_path)

    # Both DocTypes restricted alike: scoped, and nothing else reaches them.
    assert roles["even"] == [("Moderator", "Section", "news"), ("Storekeeper", None, None)]
    # Page news+press but Section news only - a scope would widen Section: untouched.
    assert roles["uneven"] == [("Moderator", None, None)]
    # Restricted on Memo, free on Letter - a scope would narrow Letter: untouched.
    assert roles["clerk"] == [("Clerk", None, None)]
    # Letter too: the clerk role is scoped, the User Permission stays for the All rule.
    assert roles["clerk2"] == [("Clerk", "Department", "IT")]
    # A holder of "*" isn't touched at all.
    assert roles["boss"] == [("Admin", None, None), ("Moderator", None, None)]
    # A MultiLink sets no scope.
    assert roles["tagger"] == [("Tagger", None, None)]
    # Archivist reaches only Memo: scoped. Clerk reaches Letter too: untouched - and
    # the User Permission stays for it.
    assert roles["archivist"] == [("Archivist", "Department", "IT"), ("Clerk", None, None)]

    # Deleted only where every path is scoped now.
    assert left == ["a1", "b1", "c1", "c2", "t1", "u1", "u2", "u3"]


def test_a_share_keeps_the_user_permission(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        _setup(conn)
        conn.execute(
            sa.text(
                "INSERT INTO grunt_permissions_shared_with VALUES ('s1', 'Page', 'P-1', 'even')"
            )
        )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        left = conn.execute(
            sa.text(
                "SELECT name FROM grunt_permissions_user_permission "
                "WHERE for_user='even' ORDER BY name"
            )
        ).all()
        scoped = conn.execute(
            sa.text("SELECT scope_value FROM grunt_auth_user_role WHERE parent_name='even'")
        ).all()
    # The role is scoped; the share on Page keeps the Page restriction, not Section's.
    assert ("news",) in [tuple(r) for r in scoped]
    assert [r[0] for r in left] == ["e1"]


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
