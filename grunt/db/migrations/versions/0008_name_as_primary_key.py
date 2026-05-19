"""Remove UUID `id` column — `name` becomes the sole primary key.

Every DocType table previously had two identifiers:
  id   — String(36) UUID, the physical PRIMARY KEY
  name — String(255), the user-visible key (e.g. INV-00001, hash, etc.)

After this migration `name` is the sole PK; `id` is dropped.
Child tables lose `parent_id` (UUID) and gain `parent_name` (String(255)).
grunt_core_multi_link loses its own `id` column and gets a composite PK.

Revision ID: 0008_name_as_primary_key
Revises: 0007_fix_page_metadata
Create Date: 2026-05-18
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0008_name_as_primary_key"
down_revision = "0007_fix_page_metadata"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Tables managed by GruntBase (system ORM tables)
_SYSTEM_TABLES = ("grunt_meta_doctype", "grunt_meta_installed_app")

# The junction table used for MultiLink fields
_MULTI_LINK_TABLE = "grunt_core_multi_link"


# ── Helpers ────────────────────────────────────────────────────────────────


def _col_exists(conn: sa.engine.Connection, table: str, column: str) -> bool:
    """Return True if *column* exists in *table* (dialect-portable)."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        return any(r[1] == column for r in rows)
    else:
        result = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
        return result.fetchone() is not None


def _table_exists(conn: sa.engine.Connection, table: str) -> bool:
    return conn.dialect.has_table(conn, table)


def _list_grunt_tables(conn: sa.engine.Connection) -> list[str]:
    """Return all table names that start with 'grunt_' (dialect-portable)."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'grunt_%'")
        ).fetchall()
        return [r[0] for r in rows]
    else:
        rows = conn.execute(
            sa.text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name LIKE 'grunt_%'"
            )
        ).fetchall()
        return [r[0] for r in rows]


# ── Per-dialect table rebuild (SQLite cannot DROP/ALTER PK) ───────────────


def _rebuild_table_sqlite(conn: sa.engine.Connection, table: str, new_ddl: str) -> None:
    """SQLite: copy → rename → drop old → rename new."""
    tmp = f"_mig_{table}_new"
    conn.execute(sa.text(new_ddl.replace(f'"{table}"', f'"{tmp}"')))
    # Copy common columns
    old_cols_rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    old_cols = {r[1] for r in old_cols_rows}
    new_cols_rows = conn.execute(sa.text(f"PRAGMA table_info({tmp})")).fetchall()
    new_cols = {r[1] for r in new_cols_rows}
    common = ", ".join(f'"{c}"' for c in sorted(old_cols & new_cols))
    conn.execute(sa.text(f'INSERT INTO "{tmp}" ({common}) SELECT {common} FROM "{table}"'))
    conn.execute(sa.text(f'DROP TABLE "{table}"'))
    conn.execute(sa.text(f'ALTER TABLE "{tmp}" RENAME TO "{table}"'))


# ── System table migration ────────────────────────────────────────────────


def _migrate_system_table(conn: sa.engine.Connection, table: str) -> None:
    """Make *name* the sole PK of a system table (drop *id*)."""
    if not _table_exists(conn, table):
        return
    if not _col_exists(conn, table, "id"):
        log.info("0008: %s already migrated (no id column)", table)
        return

    log.info("0008: migrating system table %s", table)
    dialect = conn.dialect.name

    if dialect == "sqlite":
        # SQLite: recreate table without id column
        cols_rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        # Build minimal DDL for the table without `id`
        col_defs = []
        for r in cols_rows:
            col_name = r[1]
            if col_name == "id":
                continue
            col_type = r[2]
            not_null = "NOT NULL" if r[3] else ""
            pk = "PRIMARY KEY" if col_name == "name" else ""
            default = f"DEFAULT {r[4]}" if r[4] is not None else ""
            col_defs.append(f'"{col_name}" {col_type} {pk} {not_null} {default}'.strip())
        ddl = f'CREATE TABLE "{table}" ({", ".join(col_defs)})'
        _rebuild_table_sqlite(conn, table, ddl)
    else:
        # PostgreSQL / MySQL: drop id, make name the PK
        conn.execute(sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{table}_pkey"'))
        conn.execute(sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{table}_name_key"'))
        conn.execute(sa.text(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS id'))
        conn.execute(sa.text(f'ALTER TABLE "{table}" ADD PRIMARY KEY (name)'))


# ── Dynamic DocType table migration ──────────────────────────────────────


def _migrate_doctype_table(conn: sa.engine.Connection, table: str) -> None:
    """Migrate a dynamic DocType table: make name PK, add parent_name, drop id/parent_id."""
    if not _col_exists(conn, table, "id"):
        return  # already migrated or new-style table

    log.info("0008: migrating doctype table %s", table)
    dialect = conn.dialect.name
    is_child = _col_exists(conn, table, "parent_id")

    # Ensure name is populated (fallback to id)
    conn.execute(
        sa.text(
            f'UPDATE "{table}" SET name = id WHERE name IS NULL OR name = \'\''
        )
    )

    if is_child:
        # Add parent_name if missing
        if not _col_exists(conn, table, "parent_name"):
            conn.execute(
                sa.text(f'ALTER TABLE "{table}" ADD COLUMN parent_name VARCHAR(255) DEFAULT \'\'')
            )
        # Populate parent_name from parent_id (they were the same column under old scheme)
        conn.execute(
            sa.text(
                f'UPDATE "{table}" SET parent_name = parent_id '
                f'WHERE parent_name IS NULL OR parent_name = \'\''
            )
        )

    if dialect == "sqlite":
        _migrate_doctype_table_sqlite(conn, table, is_child)
    else:
        _migrate_doctype_table_pg(conn, table, is_child)


def _migrate_doctype_table_sqlite(
    conn: sa.engine.Connection, table: str, is_child: bool
) -> None:
    cols_rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    skip = {"id", "parent_id"}
    col_defs = []
    for r in cols_rows:
        col_name = r[1]
        if col_name in skip:
            continue
        col_type = r[2]
        not_null = "NOT NULL" if r[3] else ""
        pk = "PRIMARY KEY" if col_name == "name" else ""
        default = f"DEFAULT {r[4]}" if r[4] is not None else ""
        col_defs.append(f'"{col_name}" {col_type} {pk} {not_null} {default}'.strip())
    ddl = f'CREATE TABLE "{table}" ({", ".join(col_defs)})'
    _rebuild_table_sqlite(conn, table, ddl)


def _migrate_doctype_table_pg(conn: sa.engine.Connection, table: str, is_child: bool) -> None:
    # Drop existing PK on id
    conn.execute(
        sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{table}_pkey"')
    )
    # Drop unique constraint on name if any
    conn.execute(
        sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{table}_name_key"')
    )
    # Drop id column
    conn.execute(sa.text(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS id'))
    # Make name the PK
    conn.execute(sa.text(f'ALTER TABLE "{table}" ADD PRIMARY KEY (name)'))
    if is_child:
        # Drop parent_id
        conn.execute(sa.text(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS parent_id'))


# ── MultiLink table migration ─────────────────────────────────────────────


def _migrate_multi_link(conn: sa.engine.Connection) -> None:
    if not _table_exists(conn, _MULTI_LINK_TABLE):
        return
    if not _col_exists(conn, _MULTI_LINK_TABLE, "id"):
        log.info("0008: %s already migrated", _MULTI_LINK_TABLE)
        return

    log.info("0008: migrating %s", _MULTI_LINK_TABLE)
    dialect = conn.dialect.name

    # Add parent_name if not present
    if not _col_exists(conn, _MULTI_LINK_TABLE, "parent_name"):
        conn.execute(
            sa.text(
                f'ALTER TABLE "{_MULTI_LINK_TABLE}" '
                f'ADD COLUMN parent_name VARCHAR(255) NOT NULL DEFAULT \'\''
            )
        )
    # Populate parent_name from parent_id
    conn.execute(
        sa.text(
            f'UPDATE "{_MULTI_LINK_TABLE}" SET parent_name = parent_id '
            f'WHERE parent_name IS NULL OR parent_name = \'\''
        )
    )

    if dialect == "sqlite":
        ddl = f'''CREATE TABLE "{_MULTI_LINK_TABLE}" (
            parent_doctype VARCHAR(255) NOT NULL,
            parent_name    VARCHAR(255) NOT NULL,
            parent_field   VARCHAR(255) NOT NULL,
            link_doctype   VARCHAR(255) NOT NULL,
            link_name      VARCHAR(255) NOT NULL,
            idx            INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (parent_doctype, parent_name, parent_field, idx)
        )'''
        _rebuild_table_sqlite(conn, _MULTI_LINK_TABLE, ddl)
    else:
        conn.execute(
            sa.text(
                f'ALTER TABLE "{_MULTI_LINK_TABLE}" DROP CONSTRAINT IF EXISTS "{_MULTI_LINK_TABLE}_pkey"'
            )
        )
        conn.execute(
            sa.text(f'ALTER TABLE "{_MULTI_LINK_TABLE}" DROP COLUMN IF EXISTS id')
        )
        conn.execute(
            sa.text(f'ALTER TABLE "{_MULTI_LINK_TABLE}" DROP COLUMN IF EXISTS parent_id')
        )
        conn.execute(
            sa.text(
                f'ALTER TABLE "{_MULTI_LINK_TABLE}" ADD PRIMARY KEY '
                f'(parent_doctype, parent_name, parent_field, idx)'
            )
        )


# ── Entry points ──────────────────────────────────────────────────────────


def upgrade() -> None:
    conn = op.get_bind()

    # 1. System tables (GruntBase ORM tables)
    for tbl in _SYSTEM_TABLES:
        try:
            _migrate_system_table(conn, tbl)
        except Exception as exc:
            log.warning("0008: system table %s migration failed — %s", tbl, exc)

    # 2. Dynamic DocType tables
    all_tables = _list_grunt_tables(conn)
    skip = set(_SYSTEM_TABLES) | {_MULTI_LINK_TABLE}
    for tbl in all_tables:
        if tbl in skip:
            continue
        try:
            _migrate_doctype_table(conn, tbl)
        except Exception as exc:
            log.warning("0008: table %s migration failed — %s", tbl, exc)

    # 3. MultiLink junction table
    try:
        _migrate_multi_link(conn)
    except Exception as exc:
        log.warning("0008: multi_link migration failed — %s", exc)


def downgrade() -> None:
    # Restoring UUID id columns is not practical — treat as irreversible.
    pass
