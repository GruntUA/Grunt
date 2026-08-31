"""Drop the standalone DocTypePermission store; permissions live inline on DocType.

The framework used to keep permissions in two places: inline on each DocType
(`doctype.permissions`, stored in the `grunt_meta_doctype.data` JSON blob) and
in a standalone `grunt_metadata_doc_type_permission` table that overrode the
inline copy at startup. The standalone doctype, its table and the whole
sync/migrate machinery are gone — the inline list edited in the Studio DocType
builder is now the single source of truth.

This migration folds any rows that lived only in the standalone table back into
the owning DocType's `permissions` (replace semantics, mirroring the old
`load_all_permissions_from_db`), then drops the table.

Revision ID: 0009_drop_doc_type_permission
Revises: 0008_name_as_primary_key
Create Date: 2026-08-31
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0009_drop_doc_type_permission"
down_revision = "0008_name_as_primary_key"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_PERM_TABLE = "grunt_metadata_doc_type_permission"
_BOOL_FIELDS = ("read", "write", "create", "delete", "submit", "cancel", "report")


def _row_to_perm(row: sa.engine.Row) -> dict:
    m = row._mapping
    hf_raw = (m.get("hidden_fields") or "").strip()
    perm: dict = {"role": m.get("role") or ""}
    for f in _BOOL_FIELDS:
        perm[f] = bool(m.get(f))
    perm["match"] = m.get("match") or None
    perm["hidden_fields"] = [p.strip() for p in hf_raw.split(",") if p.strip()] if hf_raw else []
    return perm


def upgrade() -> None:
    conn = op.get_bind()

    if not conn.dialect.has_table(conn, _PERM_TABLE):
        return

    meta = sa.MetaData()
    perm_tbl = sa.Table(_PERM_TABLE, meta, autoload_with=conn)
    meta_dt = sa.Table("grunt_meta_doctype", meta, autoload_with=conn)

    by_doctype: dict[str, list[dict]] = {}
    for row in conn.execute(sa.select(perm_tbl)):
        dn = row._mapping.get("doctype_name") or ""
        if dn:
            by_doctype.setdefault(dn, []).append(_row_to_perm(row))

    for dn, perms in by_doctype.items():
        res = conn.execute(
            sa.select(meta_dt.c.data).where(meta_dt.c.name == dn)
        ).first()
        if res is None:
            log.warning("0009: DocType %s has permission rows but no meta row — skipped", dn)
            continue
        data = res[0]
        if isinstance(data, str):
            data = json.loads(data)
        data["permissions"] = perms
        conn.execute(
            meta_dt.update().where(meta_dt.c.name == dn).values(data=data)
        )
        log.info("0009: folded %d permission row(s) into DocType %s", len(perms), dn)

    op.drop_table(_PERM_TABLE)
    log.info("0009: dropped %s", _PERM_TABLE)


def downgrade() -> None:
    # The standalone permission store is gone for good — irreversible.
    pass
