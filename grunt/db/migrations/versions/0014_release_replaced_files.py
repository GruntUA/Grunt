"""Detach files that a document's edit dropped (a replaced cover, a cut image).

A file referenced from a document's field is bound to it on save
(grunt.storage.references) and ``File.before_delete`` refuses files attached to
an existing document. Until now an edit that dropped the file never unbound it,
so a replaced photo could not be deleted although only the version history
still mentioned it. Saves release such files now; this does it for the past.

A file is released when the document's history (DocVersion) once referenced it
and the document - its row and child-table rows - no longer does. Attachments
the document never referenced from a field are left alone. Files are only
detached (they stay in the library), never deleted.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-19
"""

import re
from collections import Counter

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_FILE = "grunt_storage_file"
_VERSION = "grunt_doc_version"
_META = "grunt_metadata_doc_type"
_FILE_ID = re.compile(r"file_id=([A-Za-z0-9_-]+)")


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if not {_FILE, _VERSION, _META} <= tables:
        return

    from grunt.metadata.compiler import get_table_name

    # (doctype, doc id, file id) the history ever mentioned.
    mentioned: set[tuple[str, str, str]] = set()
    rows = conn.execute(
        sa.text(
            f"SELECT ref_doctype, doc_id, changes FROM {_VERSION} WHERE changes LIKE '%file_id=%'"
        )
    )
    for dt, doc_id, changes in rows:
        for fid in _FILE_ID.findall(str(changes)):
            mentioned.add((dt, doc_id, fid))

    files = conn.execute(
        sa.text(
            f"SELECT name, attached_to_doctype, attached_to_id FROM {_FILE} "
            "WHERE attached_to_doctype IS NOT NULL AND attached_to_doctype != '' "
            "AND attached_to_id IS NOT NULL AND attached_to_id != ''"
        )
    ).all()
    candidates = [(dt, doc, fid) for fid, dt, doc in files if (dt, doc, fid) in mentioned]
    if not candidates:
        return

    table_of = {
        name: table or get_table_name(module, name)
        for name, module, table in conn.execute(
            sa.text(f"SELECT name, module, table_name FROM {_META}")
        )
    }
    # Child tables by the parent DocType whose rows they hold.
    child_tables: dict[str, list[str]] = {}
    inspector = sa.inspect(conn)
    for t in tables:
        if {"parent_doctype", "parent_name"} <= {c["name"] for c in inspector.get_columns(t)}:
            for (parent,) in conn.execute(sa.text(f'SELECT DISTINCT parent_doctype FROM "{t}"')):
                child_tables.setdefault(parent, []).append(t)

    def used_ids(dt: str, doc: str) -> set[str] | None:
        """File ids the document's row and child rows mention; None if it's gone."""
        table = table_of.get(dt)
        if table not in tables:
            return None
        row = conn.execute(sa.text(f'SELECT * FROM "{table}" WHERE name = :n'), {"n": doc}).first()
        if row is None:
            return None
        text = " ".join(str(v) for v in row if v is not None)
        for child in child_tables.get(dt, []):
            for crow in conn.execute(
                sa.text(f'SELECT * FROM "{child}" WHERE parent_doctype = :d AND parent_name = :n'),
                {"d": dt, "n": doc},
            ):
                text += " " + " ".join(str(v) for v in crow if v is not None)
        return set(_FILE_ID.findall(text))

    used: dict[tuple[str, str], set[str] | None] = {}
    released: Counter[str] = Counter()
    file_tbl = sa.table(
        _FILE, sa.column("name"), sa.column("attached_to_doctype"), sa.column("attached_to_id")
    )
    for dt, doc, fid in candidates:
        if (dt, doc) not in used:
            used[dt, doc] = used_ids(dt, doc)
        ids = used[dt, doc]
        if ids is None or fid in ids:
            continue
        conn.execute(
            sa.update(file_tbl)
            .where(file_tbl.c.name == fid)
            .values(attached_to_doctype=None, attached_to_id=None)
        )
        released[dt] += 1

    if released:
        summary = ", ".join(f"{dt}: {n}" for dt, n in released.most_common())
        print(f"  storage: released {sum(released.values())} replaced file(s) ({summary})")


def downgrade() -> None:
    pass  # Detached files are ordinary library files; nothing to undo.
