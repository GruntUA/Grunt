"""Site backups — database, uploaded files and site config, on a schedule.

One backup is a *set* of files sharing an id (``20260923-020000``) in
``sites/<site>/backups/``:

* ``<id>-database.sqlite.gz`` — SQLite: an online snapshot through SQLite's
  backup API (consistent under WAL, unlike copying the file), checked with
  ``PRAGMA quick_check`` before it is kept; or ``<id>-database.pgdump`` —
  PostgreSQL ``pg_dump -Fc``;
* ``<id>-files.tar.gz`` — the site's ``uploads/`` (local storage only);
* ``<id>-config.env`` — the site ``.env`` (SECRET_KEY, DB credentials — a
  restore needs it); readable by the owner only.

``SystemSettings`` → «Резервні копії» turns the schedule on/off, sets the
interval, how many sets to keep and whether files are included. An hourly job
(:func:`grunt.backups.tasks.scheduled_backup`) makes a backup when one is due.
"""

from __future__ import annotations

import asyncio
import gzip
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from grunt.i18n import _
from grunt.log import log

KINDS = ("database", "files", "config")
_NAME = re.compile(r"^(\d{8}-\d{6})-(database|files|config)(\..+)$")


class BackupError(RuntimeError):
    pass


@dataclass
class BackupSet:
    id: str
    files: dict[str, Path] = field(default_factory=dict)  # kind → path

    @property
    def created_at(self) -> datetime:
        return datetime.strptime(self.id, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)

    def size(self, kind: str | None = None) -> int:
        paths = [self.files[kind]] if kind else list(self.files.values())
        return sum(p.stat().st_size for p in paths if p.exists())


# ── Where things are ──────────────────────────────────────────────────────


def site_dir(site: str) -> Path:
    from grunt.site.manager import site_manager

    return site_manager.sites_dir / site


def backups_dir(site: str) -> Path:
    path = site_dir(site) / "backups"
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def _db_url(site: str):
    from grunt.site.manager import site_manager

    return site_manager.get_engine(site).url


# ── Listing / rotation ────────────────────────────────────────────────────


def list_backups(site: str) -> list[BackupSet]:
    """Backup sets of *site*, newest first."""
    sets: dict[str, BackupSet] = {}
    for path in backups_dir(site).iterdir():
        m = _NAME.match(path.name)
        if m and path.is_file():
            sets.setdefault(m.group(1), BackupSet(m.group(1))).files[m.group(2)] = path
    return sorted(sets.values(), key=lambda s: s.id, reverse=True)


def get_backup(site: str, backup_id: str) -> BackupSet | None:
    return next((b for b in list_backups(site) if b.id == backup_id), None)


def delete_backup(site: str, backup_id: str) -> None:
    backup = get_backup(site, backup_id)
    if backup:
        for path in backup.files.values():
            path.unlink(missing_ok=True)


def rotate(site: str, keep: int) -> list[str]:
    """Delete all but the *keep* newest sets; returns the deleted ids."""
    removed = [b.id for b in list_backups(site)[max(keep, 1) :]]
    for backup_id in removed:
        delete_backup(site, backup_id)
    return removed


# ── Making a backup ───────────────────────────────────────────────────────


def _backup_sqlite(db_path: Path, dest: Path) -> None:
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        snapshot = Path(tmp) / "snapshot.sqlite"
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(snapshot)
        try:
            src.backup(dst)  # consistent snapshot, readers/writers keep working
            result = dst.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            dst.close()
            src.close()
        if result != "ok":
            raise BackupError(
                _("The database snapshot is corrupted: %(result)s") % {"result": result}
            )
        with snapshot.open("rb") as fin, gzip.open(dest, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout, length=1024 * 1024)


def _libpq_url(url) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _backup_postgres(url, dest: Path) -> None:
    if not shutil.which("pg_dump"):
        raise BackupError(_("pg_dump not found; install the PostgreSQL client"))
    subprocess.run(["pg_dump", "-Fc", "-f", str(dest), _libpq_url(url)], check=True)


def _backup_files(uploads: Path, dest: Path) -> None:
    with tarfile.open(dest, "w:gz", compresslevel=6) as tar:
        tar.add(uploads, arcname="uploads")


def _create_backup_sync(
    site: str, with_database: bool, with_files: bool, with_config: bool
) -> BackupSet:
    backup_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out = backups_dir(site)
    url = _db_url(site)
    made: list[Path] = []
    try:
        backend = url.get_backend_name()
        if with_database and backend == "sqlite":
            dest = out / f"{backup_id}-database.sqlite.gz"
            made.append(dest)
            _backup_sqlite(Path(url.database), dest)
        elif with_database and backend == "postgresql":
            dest = out / f"{backup_id}-database.pgdump"
            made.append(dest)
            _backup_postgres(url, dest)
        elif with_database:
            raise BackupError(_("Backups of %(backend)s are not supported") % {"backend": backend})

        uploads = site_dir(site) / "uploads"
        if with_files and uploads.is_dir():
            dest = out / f"{backup_id}-files.tar.gz"
            made.append(dest)
            _backup_files(uploads, dest)

        env = site_dir(site) / ".env"
        if with_config and env.exists():
            dest = out / f"{backup_id}-config.env"
            made.append(dest)
            shutil.copyfile(env, dest)
        for path in made:
            os.chmod(path, 0o600)
    except BaseException:
        for path in made:  # never leave a half-made set behind
            path.unlink(missing_ok=True)
        raise
    backup = get_backup(site, backup_id)
    if backup is None:
        raise BackupError(_("Nothing to back up"))
    return backup


async def create_backup(
    site: str,
    *,
    with_database: bool = True,
    with_files: bool = True,
    with_config: bool = True,
) -> BackupSet:
    """Make a backup set of *site* (the heavy work runs off the event loop)."""
    started = datetime.now(UTC)
    backup = await asyncio.to_thread(
        _create_backup_sync, site, with_database, with_files, with_config
    )
    log.info(
        "backup.created",
        site=site,
        id=backup.id,
        kinds=sorted(backup.files),
        size=backup.size(),
        seconds=round((datetime.now(UTC) - started).total_seconds(), 1),
    )
    return backup


# ── Restoring ─────────────────────────────────────────────────────────────


def restore_backup(site: str, backup: BackupSet, *, with_files: bool = False) -> Path:
    """Put a backup back in place. The server and worker must be stopped.

    The current database (and uploads, with *with_files*) are moved aside to
    ``backups/pre-restore-<time>/`` first, so a restore can itself be undone.
    Returns that directory.
    """
    if "database" not in backup.files:
        raise BackupError(_("This backup has no database"))
    aside = backups_dir(site) / f"pre-restore-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    aside.mkdir(mode=0o700)
    url = _db_url(site)

    if url.get_backend_name() == "sqlite":
        db_path = Path(url.database)
        restored = aside / "restored.sqlite"
        with gzip.open(backup.files["database"], "rb") as fin, restored.open("wb") as fout:
            shutil.copyfileobj(fin, fout, length=1024 * 1024)
        check = sqlite3.connect(restored)
        try:
            result = check.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            check.close()
        if result != "ok":
            raise BackupError(
                _("The database backup is corrupted: %(result)s") % {"result": result}
            )
        for suffix in ("", "-wal", "-shm"):
            current = Path(f"{db_path}{suffix}")
            if current.exists():
                shutil.move(current, aside / current.name)
        shutil.move(restored, db_path)
    elif url.get_backend_name() == "postgresql":
        if not shutil.which("pg_restore"):
            raise BackupError(_("pg_restore not found; install the PostgreSQL client"))
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "-d",
                _libpq_url(url),
                str(backup.files["database"]),
            ],
            check=True,
        )
    else:
        raise BackupError(
            _("Restoring %(backend)s is not supported") % {"backend": url.get_backend_name()}
        )

    if with_files and "files" in backup.files:
        uploads = site_dir(site) / "uploads"
        if uploads.exists():
            shutil.move(uploads, aside / "uploads")
        with tarfile.open(backup.files["files"], "r:gz") as tar:
            tar.extractall(site_dir(site), filter="data")
    log.info("backup.restored", site=site, id=backup.id, aside=str(aside))
    return aside
