"""Site backups - database, uploaded files and site config, on a schedule.

One backup is a *set* of files sharing an id (``20260923-020000``) in
``sites/<site>/backups/``:

* ``<id>-database<suffix>`` - the database dump, made by the site's dialect
  (``Dialect.dump``): ``.sqlite.zst`` - an online SQLite snapshot checked with
  ``PRAGMA quick_check``; ``.pgdump`` - PostgreSQL ``pg_dump -Fc``;
* ``<id>-files.tar.zst`` - the site's ``uploads/`` - only what is on this
  disk: files moved to cloud storage are kept there, not in the set;
* ``<id>-config.env`` - the site ``.env`` (SECRET_KEY, DB credentials - a
  restore needs it); readable by the owner only.

``SystemSettings`` -> «Резервні копії» turns the schedule on/off, sets the
interval, how many sets to keep, whether files are included and the zstd
compression level. An hourly job
(:func:`grunt.backups.tasks.scheduled_backup`) makes a backup when one is due.
"""

import asyncio
import contextlib
import fcntl
import os
import re
import shutil
import tarfile
from collections.abc import Callable, Sequence
from compression import zstd
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from grunt import _, log
from grunt.db.dialects import dialect_for
from grunt.progress import Progress
from grunt.site.manager import site_manager

KINDS = ("database", "files", "config")
# zstd 9: ~40% smaller than gzip 6 and faster; 19 squeezes more at ~25× the time.
DEFAULT_COMPRESSION_LEVEL = 9
MAX_COMPRESSION_LEVEL = 19
# The name becomes a path: the suffix is extension characters only (no "/").
_NAME = re.compile(r"^(\d{8}-\d{6})-(database|files|config)(\.[A-Za-z0-9.]+)$")


class BackupError(RuntimeError):
    pass


class BackupBusyError(BackupError):
    """Another backup of the site is being made right now."""


@dataclass
class BackupSet:
    id: str
    files: dict[str, Path] = field(default_factory=dict)  # kind -> path

    @property
    def created_at(self) -> datetime:
        return datetime.strptime(self.id, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)

    def size(self, kind: str | None = None) -> int:
        paths = [self.files[kind]] if kind else list(self.files.values())
        return sum(p.stat().st_size for p in paths if p.exists())


# Where things are


def site_dir(site: str) -> Path:
    return site_manager.sites_dir / site


def backups_dir(site: str) -> Path:
    path = site_dir(site) / "backups"
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def _db_url(site: str):
    return site_manager.get_engine(site).url


# Listing / rotation


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


# Making a backup


def zstd_options(level: int) -> dict:
    """Compression *level* (clamped) on half the cores - the site keeps serving meanwhile."""
    options = {
        zstd.CompressionParameter.compression_level: min(max(level, 1), MAX_COMPRESSION_LEVEL)
    }
    workers = max((os.cpu_count() or 1) // 2, 1)
    if workers > 1 and zstd.CompressionParameter.nb_workers.bounds()[1] > 0:
        options[zstd.CompressionParameter.nb_workers] = workers
    return options


class _CountingReader:
    """A file whose reads advance *progress* - a big file moves the bar as it goes."""

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


_SKIPPED_UPLOADS = ("uploads/tmp/", "uploads/cache/")


def _backup_files(uploads: Path, dest: Path, level: int, progress: Progress) -> None:
    progress.set(stage=_("Archiving files"))
    with _CountingTarFile.open(dest, "w:zst", options=zstd_options(level)) as tar:
        tar.progress = progress
        # Uploads still in flight (tmp/) are not files yet; cache/ holds copies
        # of files kept in cloud storage (grunt.storage.cloud.files) - they
        # are safe there and would only bloat every set.
        tar.add(
            uploads,
            arcname="uploads",
            filter=lambda info: None if info.name.startswith(_SKIPPED_UPLOADS) else info,
        )


def _backup_config(env: Path, dest: Path, progress: Progress) -> None:
    progress.set(stage=_("Copying the configuration"))
    shutil.copyfile(env, dest)


def _part(path: Path) -> Path:
    """Where *path* is written until the whole set is done - hidden, not matched by _NAME.

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


@contextlib.contextmanager
def _exclusive(site: str):
    """One backup of a site at a time - across the worker's threads and the CLI.

    Hourly jobs that piled up while the worker was busy all start together
    once it is free again; without this each would make its own full set
    side by side and fill the disk.
    """
    with (site_dir(site) / ".backup.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupBusyError(_("Another backup is being made right now")) from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


# Room for one more set besides the ones rotation keeps until it succeeds
_SPACE_MARGIN = 1.1


class _Step(NamedTuple):
    """One part of a set: bytes it reads (the bar), bytes it may take on disk,
    its final path and how to make it (into the path it is given)."""

    read: int
    space: int
    dest: Path
    make: Callable[[Path], object]


def _space_needed(steps: Sequence[_Step], latest: BackupSet | None, scratch: int) -> int:
    """Bytes the new set needs on disk: as big as the latest set of the same parts
    (or the steps' own estimate, if there is none), plus *scratch* - what a part
    needs only while it is made (an uncompressed SQLite snapshot)."""
    need = 0
    for step in steps:
        match = _NAME.match(step.dest.name)
        assert match is not None, step.dest.name  # create_backup names every part to fit
        kind = match.group(2)
        need += latest.size(kind) if latest and kind in latest.files else step.space
    return int((need + scratch) * _SPACE_MARGIN)


def _check_space(out: Path, need: int) -> None:
    free = shutil.disk_usage(out).free
    if free < need:
        raise BackupError(
            _("Not enough disk space for a backup: %(need)s needed, %(free)s free")
            % {"need": _gb(need), "free": _gb(free)}
        )


def _gb(size: int) -> str:
    return f"{size / 1024**3:.1f} GB"


def _tree_size(path: Path) -> int:
    """Bytes the files archive reads - what _backup_files skips doesn't count."""
    skipped = tuple(path / p.removeprefix("uploads/") for p in _SKIPPED_UPLOADS)
    return sum(
        p.stat().st_size
        for p in path.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and not any(p.is_relative_to(folder) for folder in skipped)
    )


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
    dialect = dialect_for(url)
    uploads = site_dir(site) / "uploads"
    with_files = with_files and uploads.is_dir()

    if with_database and dialect.dump_suffix is None:
        raise BackupError(_("Backups of %(backend)s are not supported") % {"backend": dialect.name})
    env = site_dir(site) / ".env"

    # Quickest first, by the bytes each part reads: the config is a copy of one
    # small file; the database and the files go by size. The bar is measured in
    # those bytes (a SQLite file twice - snapshot, then compressing it; every
    # uploaded file); a pg_dump's size is unknown - it shows its stage only.
    progress.set(stage=_("Preparing"))
    steps: list[_Step] = []
    scratch = 0
    if with_config and env.exists():
        steps.append(
            _Step(
                0,
                0,
                out / f"{backup_id}-config.env",
                lambda part: _backup_config(env, part, progress),
            )
        )
    if with_database:
        estimate = dialect.dump_estimate(url)
        scratch = estimate.scratch
        steps.append(
            _Step(
                estimate.read,
                estimate.output,
                out / f"{backup_id}-database{dialect.dump_suffix}",
                lambda part: dialect.dump(url, part, level, progress),
            )
        )
    if with_files:
        size = _tree_size(uploads)
        steps.append(
            _Step(
                size,
                size,
                out / f"{backup_id}-files.tar.zst",
                lambda part: _backup_files(uploads, part, level, progress),
            )
        )
    steps.sort(key=lambda step: step.read)  # stable: the config stays ahead of a pg_dump
    progress.set(total=sum(step.read for step in steps), steps=len(steps))

    _remove_stale_parts(out)
    backups = list_backups(site)
    _check_space(out, _space_needed(steps, backups[0] if backups else None, scratch))
    made: list[Path] = []  # the final paths; each is written as its _part() first
    try:
        for number, step in enumerate(steps, 1):
            progress.set(step=number)
            made.append(step.dest)
            step.make(_part(step.dest))
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


def _locked_create_backup(site: str, *args) -> BackupSet:
    with _exclusive(site):
        return _create_backup_sync(site, *args)


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
        _locked_create_backup, site, with_database, with_files, with_config, level, progress
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


# Restoring


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

    dialect_for(url).restore_dump(url, backup.files["database"], aside)

    if with_files and "files" in backup.files:
        uploads = site_dir(site) / "uploads"
        if uploads.exists():
            shutil.move(uploads, aside / "uploads")
        with tarfile.open(backup.files["files"], "r:zst") as tar:
            tar.extractall(site_dir(site), filter="data")
    log.info("backup.restored", site=site, id=backup.id, aside=str(aside))
    return aside
