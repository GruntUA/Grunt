"""Backfill WebFormField rows from the legacy WebForm.fields JSON column.

WebForm.fields changed from a JSON blob to a Table(WebFormField) child
relation. Schema sync (``grunt db migrate``'s DocType-table step) only adds
columns/tables - it never migrates data across a type change, so any site
that already had a WebForm before this change loses that form's field list
the moment the new schema lands (the old JSON blob is left behind, orphaned,
on the parent row, until this migration runs).

Revision ID: 0001
Revises:
Create Date: 2026-09-16
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_PARENT_TABLE = "grunt_web_form"
_CHILD_TABLE = "grunt_site_web_form_field"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if _PARENT_TABLE not in tables or _CHILD_TABLE not in tables:
        return  # WebForm/WebFormField not installed on this site

    parent_cols = {c["name"] for c in inspector.get_columns(_PARENT_TABLE)}
    if "fields" not in parent_cols:
        return  # legacy column already gone - nothing to backfill

    child = sa.table(
        _CHILD_TABLE,
        sa.column("name"),
        sa.column("owner"),
        sa.column("created_at"),
        sa.column("modified_at"),
        sa.column("modified_by"),
        sa.column("docstatus"),
        sa.column("parent_name"),
        sa.column("parent_doctype"),
        sa.column("parent_field"),
        sa.column("idx"),
        sa.column("fieldname"),
        sa.column("fieldtype"),
        sa.column("label"),
        sa.column("required"),
        sa.column("hidden"),
        sa.column("collapsible"),
        sa.column("description"),
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    rows = conn.execute(sa.text(f"SELECT name, owner, fields FROM {_PARENT_TABLE}")).fetchall()

    for form_name, owner, fields_json in rows:
        if not fields_json:
            continue

        already = conn.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {_CHILD_TABLE} "
                "WHERE parent_name = :p AND parent_doctype = 'WebForm'"
            ),
            {"p": form_name},
        ).scalar()
        if already:
            continue  # real rows already exist - a fresh insert, don't duplicate

        try:
            entries = json.loads(fields_json)
        except TypeError, ValueError:
            continue
        if not isinstance(entries, list):
            continue

        owner = owner or "system@grunt.local"
        insert_rows = []
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict) or not entry.get("fieldname"):
                continue
            insert_rows.append(
                {
                    "name": uuid.uuid4().hex[:10],
                    "owner": owner,
                    "created_at": now,
                    "modified_at": now,
                    "modified_by": owner,
                    "docstatus": 0,
                    "parent_name": form_name,
                    "parent_doctype": "WebForm",
                    "parent_field": "fields",
                    "idx": idx,
                    "fieldname": entry["fieldname"],
                    "fieldtype": entry.get("fieldtype") or "",
                    "label": entry.get("label") or "",
                    "required": bool(entry.get("required")),
                    "hidden": bool(entry.get("hidden")),
                    "collapsible": bool(entry.get("collapsible")),
                    "description": entry.get("description") or "",
                }
            )
        if insert_rows:
            conn.execute(sa.insert(child), insert_rows)

    with op.batch_alter_table(_PARENT_TABLE) as batch:
        batch.drop_column("fields")


def downgrade() -> None:
    op.add_column(_PARENT_TABLE, sa.Column("fields", sa.Text(), nullable=True))
    # Data isn't restored to the JSON column - the child rows remain as the
    # source of truth even after downgrade rather than being deleted.
