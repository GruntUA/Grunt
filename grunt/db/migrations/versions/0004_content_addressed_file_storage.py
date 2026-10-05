"""Move uploaded files to content-addressed storage.

Files used to live at ``uploads/YYYY/MM/<uuid>.<ext>`` with the location kept
in ``File.path`` (and the preview's in ``File.thumbnail_path``). They now live
at ``uploads/blobs/ab/cd/<sha256>`` (previews ``uploads/thumbs/…/<sha256>.webp``)
and a ``File`` row only needs its ``content_hash`` (grunt.storage.backends).

For every ``File`` row (and every ``File`` snapshot in the trash): fill the
hash if it is missing, move the file into ``blobs/`` (identical copies
collapse into one), move the preview into ``thumbs/``. Files no row refers to
are moved aside to ``uploads/orphaned/`` - not deleted. Then the ``path`` and
``thumbnail_path`` columns are dropped.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from pathlib import Path

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TABLE = "grunt_storage_file"
_TRASH = "grunt_log_deleted_document"
_NEW_DIRS = {"blobs", "thumbs", "tmp", "orphaned"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class _Mover:
    def __init__(self, backend) -> None:
        self.backend = backend
        self.root: Path = backend.root
        self.moved: set[Path] = set()
        self.keys: dict[str, str] = {}  # rows may share a path (old dedupe_storage)

    def blob(self, rel: str | None, key: str | None) -> str | None:
        """Put the file at *rel* into ``blobs/``; return its hash (or *key*)."""
        if rel and rel in self.keys:
            return key or self.keys[rel]
        src = self.root / rel if rel else None
        if src is None or not src.is_file():
            return key
        key = key or _sha256(src)
        self.keys[rel] = key  # type: ignore[index]
        dest = self.backend.path(key)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dest)
        self.moved.add(src)
        return key

    def thumb(self, rel: str | None, key: str | None) -> None:
        src = self.root / rel if rel else None
        if not key or src is None or not src.is_file():
            return
        dest = self.backend.thumbnail_path(key)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dest)
        self.moved.add(src)

    def finish(self) -> int:
        """Drop moved duplicates; set aside what nothing referenced; prune dirs."""
        for src in self.moved:
            src.unlink(missing_ok=True)
        orphaned = 0
        for top in list(self.root.iterdir()) if self.root.is_dir() else []:
            if top.name in _NEW_DIRS or not top.is_dir():
                continue
            for path in sorted(top.rglob("*")):
                if path.is_file():
                    dest = self.root / "orphaned" / path.relative_to(self.root)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(path, dest)
                    orphaned += 1
            for folder in sorted(top.rglob("*"), reverse=True):
                if folder.is_dir():
                    folder.rmdir()
            top.rmdir()
        return orphaned


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if "path" not in cols:
        return  # already content-addressed

    from grunt.storage.backends import get_storage_backend

    mover = _Mover(get_storage_backend())
    has_thumb = "thumbnail_path" in cols

    tbl = sa.table(_TABLE, sa.column("name"), sa.column("content_hash"))
    select_cols = ["name", "path", "content_hash"] + (["thumbnail_path"] if has_thumb else [])
    rows = conn.execute(sa.text(f"SELECT {', '.join(select_cols)} FROM {_TABLE}")).mappings()
    for row in list(rows):
        key = mover.blob(row["path"], row["content_hash"])
        mover.thumb(row.get("thumbnail_path"), key)
        if key and key != row["content_hash"]:
            conn.execute(sa.update(tbl).where(tbl.c.name == row["name"]).values(content_hash=key))

    # A trashed File keeps its blob too - and must still find it once restored.
    if _TRASH in inspector.get_table_names():
        trash = sa.table(_TRASH, sa.column("name"), sa.column("data"))
        snapshots = conn.execute(
            sa.text(f"SELECT name, data FROM {_TRASH} WHERE deleted_doctype = 'File'")
        ).mappings()
        for snap in list(snapshots):
            data = snap["data"]
            if isinstance(data, str):
                data = json.loads(data)
            if not isinstance(data, dict) or "path" not in data:
                continue
            data["content_hash"] = mover.blob(data.pop("path"), data.get("content_hash"))
            mover.thumb(data.pop("thumbnail_path", None), data["content_hash"])
            conn.execute(
                sa.update(trash).where(trash.c.name == snap["name"]).values(data=json.dumps(data))
            )

    orphaned = mover.finish()
    if orphaned:
        print(f"  storage: {orphaned} unreferenced file(s) moved to {mover.root / 'orphaned'}")

    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column("path")
        if has_thumb:
            batch.drop_column("thumbnail_path")


def downgrade() -> None:
    raise NotImplementedError("Content-addressed storage can't be moved back to dated paths.")
