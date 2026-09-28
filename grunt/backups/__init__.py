"""Site backups — database, uploaded files and site config, on a schedule.

One backup is a *set* of files sharing an id (``20260923-020000``) in
``sites/<site>/backups/``:

* ``<id>-database.sqlite.zst`` — SQLite: an online snapshot through SQLite's
  backup API (consistent under WAL, unlike copying the file), checked with
  ``PRAGMA quick_check`` before it is kept; or ``<id>-database.pgdump`` —
  PostgreSQL ``pg_dump -Fc``;
* ``<id>-files.tar.zst`` — the site's ``uploads/`` (local storage only);
* ``<id>-config.env`` — the site ``.env`` (SECRET_KEY, DB credentials — a
  restore needs it); readable by the owner only.

``SystemSettings`` → «Резервні копії» turns the schedule on/off, sets the
interval, how many sets to keep, whether files are included and the zstd
compression level. An hourly job
(:func:`grunt.backups.tasks.scheduled_backup`) makes a backup when one is due.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from compression import zstd
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from grunt.i18n import _
from grunt.log import log
from grunt.progress import Progress

if TYPE_CHECKING:
    from collections.abc import Callable

KINDS = ("database", "files", "config")
# zstd 9: ~40% smaller than gzip 6 and faster; 19 squeezes more at ~25× the time.
DEFAULT_COMPRESSION_LEVEL = 9
MAX_COMPRESSION_LEVEL = 19
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


def _sqlite_path(url) -> Path:
    if not url.database:  # in-memory SQLite — no file to back up or restore
        raise BackupError(_("The SQLite database has no file to back up"))
    return Path(url.database)


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


def _zstd_options(level: int) -> dict:
    """Compression *level* (clamped) on half the cores — the site keeps serving meanwhile."""
    options = {
        zstd.CompressionParameter.compression_level: min(max(level, 1), MAX_COMPRESSION_LEVEL)
    }
    workers = max((os.cpu_count() or 1) // 2, 1)
    if workers > 1 and zstd.CompressionParameter.nb_workers.bounds()[1] > 0:
        options[zstd.CompressionParameter.nb_workers] = workers
    return options


def _backup_sqlite(db_path: Path, dest: Path, level: int, progress: Progress) -> None:
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".", suffix=".part") as tmp:
        snapshot = Path(tmp) / "snapshot.sqlite"
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(snapshot)
        base = progress.done
        page_size = src.execute("PRAGMA page_size").fetchone()[0]

        def copied(_status: int, remaining: int, total: int) -> None:
            progress.set(done=base + (total - remaining) * page_size)

        try:
            progress.set(stage=_("Copying the database"))
            # consistent snapshot, readers/writers keep working between the steps
            src.backup(dst, pages=4096, progress=copied)
            progress.set(stage=_("Checking the database copy"))
            result = dst.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            dst.close()
            src.close()
        if result != "ok":
            raise BackupError(
                _("The database snapshot is corrupted: %(result)s") % {"result": result}
            )
        progress.set(done=base + snapshot.stat().st_size, stage=_("Compressing the database"))
        with (
            snapshot.open("rb") as fin,
            zstd.open(dest, "wb", options=_zstd_options(level)) as fout,
        ):
            while chunk := fin.read(1024 * 1024):
                fout.write(chunk)
                progress.advance(len(chunk))


def _libpq_url(url) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _backup_postgres(url, dest: Path, level: int, progress: Progress) -> None:
    if not shutil.which("pg_dump"):
        raise BackupError(_("pg_dump not found; install the PostgreSQL client"))
    level = min(max(level, 1), MAX_COMPRESSION_LEVEL)
    progress.set(stage=_("Dumping the database"))  # pg_dump reports no progress
    # --compress=zstd needs pg_dump 16+.
    subprocess.run(
        ["pg_dump", "-Fc", f"--compress=zstd:{level}", "-f", str(dest), _libpq_url(url)],
        check=True,
    )


class _CountingReader:
    """A file whose reads advance *progress* — a big file moves the bar as it goes."""

    def __init__(self, f, progress: Progress):
        self._f = f
        self._progress = progress

    def read(self, size: int = -1) -> bytes:
        chunk = self._f.read(size)
        self._progress.advance(len(chunk))
        return chunk


class _CountingTarFile(tarfile.TarFile):
    progress: Progress

    def addfile(self, tarinfo, fileobj=None):
        if fileobj is not None:
            fileobj = _CountingReader(fileobj, self.progress)
        super().addfile(tarinfo, fileobj)


def _backup_files(uploads: Path, dest: Path, level: int, progress: Progress) -> None:
    progress.set(stage=_("Archiving files"))
    with _CountingTarFile.open(dest, "w:zst", options=_zstd_options(level)) as tar:
        tar.progress = progress
        tar.add(uploads, arcname="uploads")


def _backup_config(env: Path, dest: Path, progress: Progress) -> None:
    progress.set(stage=_("Copying the configuration"))
    shutil.copyfile(env, dest)


def _part(path: Path) -> Path:
    """Where *path* is written until the whole set is done — hidden, not matched by _NAME.

    If the worker is killed mid-backup, only these are left behind, never a
    broken set in the list.
    """
    return path.with_name(f".{path.name}.part")


_STALE_PART = timedelta(hours=12)


def _remove_stale_parts(out: Path) -> None:
    """Leftovers of a backup that was killed (a running one's parts are fresh)."""
    cutoff = datetime.now(UTC) - _STALE_PART
    for path in out.glob(".*.part"):
        with contextlib.suppress(OSError):
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff:
                shutil.rmtree(path) if path.is_dir() else path.unlink()


def _tree_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def _create_backup_sync(
    site: str,
    with_database: bool,
    with_files: bool,
    with_config: bool,
    level: int,
    progress: Progress,
) -> BackupSet:
    backup_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out = backups_dir(site)
    url = _db_url(site)
    backend = url.get_backend_name()
    uploads = site_dir(site) / "uploads"
    with_files = with_files and uploads.is_dir()

    if with_database and backend not in ("sqlite", "postgresql"):
        raise BackupError(_("Backups of %(backend)s are not supported") % {"backend": backend})
    env = site_dir(site) / ".env"

    # Quickest first — (bytes read, final path, make it): the config is a copy
    # of one small file; the database and the files go by size. The bar is
    # measured in those bytes: a SQLite file twice (snapshot, then compressing
    # it), every uploaded file; pg_dump's size is unknown — it shows its stage only.
    progress.set(stage=_("Preparing"))
    steps: list[tuple[int, Path, Callable[[Path], object]]] = []
    if with_config and env.exists():
        steps.append(
            (0, out / f"{backup_id}-config.env", lambda part: _backup_config(env, part, progress))
        )
    if with_database and backend == "sqlite":
        db_path = _sqlite_path(url)
        steps.append(
            (
                2 * db_path.stat().st_size,
                out / f"{backup_id}-database.sqlite.zst",
                lambda part: _backup_sqlite(db_path, part, level, progress),
            )
        )
    if with_database and backend == "postgresql":
        steps.append(
            (
                0,
                out / f"{backup_id}-database.pgdump",
                lambda part: _backup_postgres(url, part, level, progress),
            )
        )
    if with_files:
        steps.append(
            (
                _tree_size(uploads),
                out / f"{backup_id}-files.tar.zst",
                lambda part: _backup_files(uploads, part, level, progress),
            )
        )
    steps.sort(key=lambda step: step[0])  # stable: the config stays ahead of a pg_dump
    progress.set(total=sum(size for size, _dest, _make in steps), steps=len(steps))

    _remove_stale_parts(out)
    made: list[Path] = []  # the final paths; each is written as its _part() first
    try:
        for step, (_size, dest, make) in enumerate(steps, 1):
            progress.set(step=step)
            made.append(dest)
            make(_part(dest))
        for path in made:
            os.chmod(_part(path), 0o600)
        for path in made:  # the set appears in the list only once it is complete
            _part(path).rename(path)
    except BaseException:
        for path in made:  # never leave a half-made set behind
            _part(path).unlink(missing_ok=True)
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
    level: int = DEFAULT_COMPRESSION_LEVEL,
    progress: Progress | None = None,
) -> BackupSet:
    """Make a backup set of *site* (the heavy work runs off the event loop).

    *progress* (see :func:`grunt.progress.track_progress`) follows it in bytes.
    """
    started = datetime.now(UTC)
    progress = progress or Progress("", user=None)
    backup = await asyncio.to_thread(
        _create_backup_sync, site, with_database, with_files, with_config, level, progress
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
        db_path = _sqlite_path(url)
        restored = aside / "restored.sqlite"
        with zstd.open(backup.files["database"], "rb") as fin, restored.open("wb") as fout:
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
        with tarfile.open(backup.files["files"], "r:zst") as tar:
            tar.extractall(site_dir(site), filter="data")
    log.info("backup.restored", site=site, id=backup.id, aside=str(aside))
    return aside
