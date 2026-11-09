"""Document history gets a size: ``DocType.max_versions`` (default 50).

Versions past each DocType's limit are deleted now, as a save deletes them
from here on (the newest are kept). On SQLite the remaining ``changes`` are
rewritten without ``\\uXXXX`` escapes - older rows were stored ASCII-escaped,
which takes three times the bytes for Cyrillic; PostgreSQL's JSONB and
MySQL's JSON store them normalized already.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-09
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_VERSION = "grunt_doc_version"
_META = "grunt_metadata_doc_type"
_DEFAULT_KEEP = 50
_BATCH = 500


def _limits(conn: sa.Connection) -> dict[str, int]:
    """``DocType -> max_versions`` for the DocTypes whose definition sets it."""
    limits: dict[str, int] = {}
    for name, definition in conn.execute(sa.text(f"SELECT name, definition FROM {_META}")):
        try:
            data = definition if isinstance(definition, dict) else json.loads(definition)
        except TypeError, ValueError:
            continue
        if isinstance(data.get("max_versions"), int):
            limits[name] = data["max_versions"]
    return limits


def _prune(conn: sa.Connection) -> None:
    limits = _limits(conn)
    over = conn.execute(
        sa.text(
            f"SELECT ref_doctype, doc_id, max(version) FROM {_VERSION} "
            "GROUP BY ref_doctype, doc_id HAVING count(*) > :keep"
        ),
        {"keep": min([_DEFAULT_KEEP, *[v for v in limits.values() if v > 0]])},
    ).all()
    for doctype, doc_id, newest in over:
        keep = limits.get(doctype, _DEFAULT_KEEP)
        if keep <= 0:
            continue
        conn.execute(
            sa.text(
                f"DELETE FROM {_VERSION} "
                "WHERE ref_doctype = :dt AND doc_id = :id AND version <= :upto"
            ),
            {"dt": doctype, "id": doc_id, "upto": newest - keep},
        )


def _unescape(conn: sa.Connection) -> None:
    after = ""
    while True:
        rows = conn.execute(
            sa.text(
                f"SELECT name, changes FROM {_VERSION} WHERE name > :after ORDER BY name LIMIT :n"
            ),
            {"after": after, "n": _BATCH},
        ).all()
        if not rows:
            return
        for name, changes in rows:
            if isinstance(changes, str) and "\\u" in changes:
                try:
                    plain = json.dumps(json.loads(changes), ensure_ascii=False)
                except ValueError:
                    continue
                if plain != changes:
                    conn.execute(
                        sa.text(f"UPDATE {_VERSION} SET changes = :c WHERE name = :n"),
                        {"c": plain, "n": name},
                    )
        after = rows[-1][0]


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if _VERSION not in tables or _META not in tables:
        return
    _prune(conn)
    if conn.dialect.name == "sqlite":
        _unescape(conn)


def downgrade() -> None:
    # Deleted versions are gone; the unescaped JSON is the same data.
    pass
