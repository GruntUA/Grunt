"""Replace ``SystemSettings.extra_file_types`` with ``allowed_file_types``.

The list of accepted upload types used to be a constant in
``grunt.storage.files`` plus a site's extra types on top; now the whole list
is the setting. Each site gets the former built-in list followed by its own
extra types, the old column is dropped and its field removed from the stored
definition (stored fields the JSON no longer has are kept as local
customisations - see 0005).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-23
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_TABLE = "grunt_site_system_settings"
_OLD, _NEW = "extra_file_types", "allowed_file_types"
# The built-in list as of this revision.
_BUILT_IN = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "application/json",
    "application/zip",
    "application/pkcs7-signature",
    "application/x-pkcs7-signature",
    "application/pkcs7-mime",
    "application/x-pkcs7-certificates",
    "application/pkix-cert",
    "application/x-x509-ca-cert",
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if _META in tables:
        meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON()))
        row = conn.execute(
            sa.select(meta.c.definition).where(meta.c.name == "SystemSettings")
        ).first()
        data = (json.loads(row[0]) if isinstance(row[0], str) else row[0]) if row else None
        if data:
            fields = data.get("fields") or []
            kept = [f for f in fields if f.get("fieldname") != _OLD]
            if len(kept) != len(fields):
                data["fields"] = kept
                conn.execute(
                    sa.update(meta).where(meta.c.name == "SystemSettings").values(definition=data)
                )

    if _TABLE not in tables:
        return
    columns = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _NEW not in columns:
        op.add_column(_TABLE, sa.Column(_NEW, sa.Text(), nullable=True))
    settings = sa.table(_TABLE, sa.column(_NEW), *([sa.column(_OLD)] if _OLD in columns else []))
    extra = ""
    if _OLD in columns:
        extra = conn.execute(sa.select(settings.c[_OLD])).scalar() or ""
    own = [t.strip() for t in extra.replace(";", ",").split(",") if t.strip()]
    value = "\n".join([*_BUILT_IN, *own])
    conn.execute(sa.update(settings).where(settings.c[_NEW].is_(None)).values({_NEW: value}))
    if _OLD in columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_OLD)


def downgrade() -> None:
    pass
