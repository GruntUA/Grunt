"""Rename a DocType in an Alembic migration - the table, its stored
definition and every reference to its name in the data.

Use from a revision's ``upgrade()``::

    from grunt.db.rename_doctype import rename_doctype

    rename_doctype(op.get_bind(), "Old", "New", new_table="grunt_new",
                   fields={"old_field": "new_field"})

What changes:

* the table (``ALTER TABLE ... RENAME``); our own ``ix_<old table>_…`` indexes
  are dropped - ``grunt migrate``'s DocType sync creates them under the new
  table's names. A table already sitting under the new name (an empty one a
  sync made) is dropped first; a non-empty one is an error;
* ``fields`` - columns renamed, and the field in the stored definition;
* the stored definition (``grunt_metadata_doc_type``): its ``name`` and
  ``table_name``; in every stored definition, ``Link``/``Table`` fields whose
  ``options`` name the DocType (Link, Table, MultiLink…);
* values naming the DocType: every column that holds DocType names - a
  ``Link`` to ``DocType``, the type column of a ``DynamicLink``, and any column
  named ``doctype`` / ``*_doctype`` (system columns like ``parent_doctype``,
  legacy tables no definition describes).

Swapping names (``A`` -> ``A2``, then ``B`` -> ``A``) works when run in that order.
Runs inside the migration's transaction; synchronous (Alembic's connection).
Safe to retry after an interrupted run (MySQL commits each DDL statement).

Revisions call this helper instead of carrying a copy, so a change here may
only extend it: what it does for the arguments an existing revision passes
must stay the same, or replaying that revision changes.
"""

import json
from typing import Any

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Connection

_META = "grunt_metadata_doc_type"


def _load(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        return json.loads(raw or "{}")
    return dict(raw or {})


def _q(conn: Connection, name: str) -> str:
    return conn.dialect.identifier_preparer.quote(name)


def _doctype_columns(conn: Connection, definitions: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """``(table, column)`` pairs that hold DocType names."""
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    pairs: set[tuple[str, str]] = set()

    by_table: dict[str, set[str]] = {}
    for data in definitions:
        table = data.get("table_name")
        if not table or table not in tables:
            continue
        for field in data.get("fields") or []:
            ftype, options = field.get("fieldtype"), field.get("options")
            if ftype == "Link" and options == "DocType":
                by_table.setdefault(table, set()).add(field["fieldname"])
            elif ftype == "DynamicLink" and isinstance(options, str) and options:
                by_table.setdefault(table, set()).add(options)

    for table in tables:
        columns = {c["name"] for c in inspector.get_columns(table)}
        wanted = {c for c in columns if c == "doctype" or c.endswith("_doctype")}
        wanted |= by_table.get(table, set()) & columns
        pairs.update((table, c) for c in wanted)
    return pairs


def rename_doctype(
    conn: Connection,
    old: str,
    new: str,
    *,
    new_table: str,
    fields: dict[str, str] | None = None,
) -> None:
    """Rename DocType *old* to *new* (table *new_table*); see the module docstring."""
    fields = fields or {}
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if _META not in tables:
        return

    meta = sa.table(
        _META,
        sa.column("name"),
        sa.column("table_name"),
        sa.column("definition", sa.JSON()),
    )
    row = conn.execute(
        sa.select(meta.c.table_name, meta.c.definition).where(meta.c.name == old)
    ).first()
    if row is None:
        return  # never installed here (or already renamed)
    if conn.execute(sa.select(meta.c.name).where(meta.c.name == new)).first():
        raise RuntimeError(f"rename_doctype: DocType {new!r} already exists")

    data = _load(row.definition)
    old_table = data.get("table_name") or row.table_name

    # 1. The table.
    if old_table and old_table in tables and old_table != new_table:
        if new_table in tables:
            count = conn.execute(sa.text(f"SELECT COUNT(*) FROM {_q(conn, new_table)}")).scalar()
            if count:
                raise RuntimeError(
                    f"rename_doctype: table {new_table!r} already exists and holds data"
                )
            conn.execute(sa.text(f"DROP TABLE {_q(conn, new_table)}"))
        # Alembic's DDL knows each dialect's syntax (MySQL: DROP INDEX … ON table).
        ops = Operations(MigrationContext.configure(conn))
        for ix in inspector.get_indexes(old_table):
            name = ix.get("name") or ""
            if name.startswith(f"ix_{old_table}_"):
                ops.drop_index(name, table_name=old_table)
        conn.execute(sa.text(f"ALTER TABLE {_q(conn, old_table)} RENAME TO {_q(conn, new_table)}"))

    # Columns - also when a previous, interrupted run already renamed the
    # table (MySQL commits each DDL statement on its own).
    if fields and new_table in set(sa.inspect(conn).get_table_names()):
        columns = {c["name"] for c in sa.inspect(conn).get_columns(new_table)}
        for old_col, new_col in fields.items():
            if old_col in columns and new_col not in columns:
                conn.execute(
                    sa.text(
                        f"ALTER TABLE {_q(conn, new_table)} "
                        f"RENAME COLUMN {_q(conn, old_col)} TO {_q(conn, new_col)}"
                    )
                )

    # 2. Its own stored definition.
    data["name"] = new
    data["table_name"] = new_table
    for field in data.get("fields") or []:
        if field.get("fieldname") in fields:
            field["fieldname"] = fields[field["fieldname"]]
    data["indexes"] = [[fields.get(c, c) for c in group] for group in (data.get("indexes") or [])]
    conn.execute(
        sa.update(meta)
        .where(meta.c.name == old)
        .values(name=new, table_name=new_table, definition=data)
    )

    # 3. Other definitions pointing at it.
    definitions: list[dict[str, Any]] = []
    for name, raw in conn.execute(sa.select(meta.c.name, meta.c.definition)).all():
        other = _load(raw)
        changed = False
        for field in other.get("fields") or []:
            # Link / Table / MultiLink …: options name the DocType.
            if field.get("options") == old and field.get("fieldtype") != "Select":
                field["options"] = new
                changed = True
        if changed:
            conn.execute(sa.update(meta).where(meta.c.name == name).values(definition=other))
        definitions.append(other)

    # 4. Values naming it.
    for table, column in sorted(_doctype_columns(conn, definitions)):
        if table == _META:
            continue
        conn.execute(
            sa.text(
                f"UPDATE {_q(conn, table)} SET {_q(conn, column)} = :new "
                f"WHERE {_q(conn, column)} = :old"
            ),
            {"new": new, "old": old},
        )
