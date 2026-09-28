"""Site backups: consistent SQLite snapshot + files + config, rotation, restore,
signed downloads, and the «Стан системи» check."""

from __future__ import annotations

import sqlite3
import stat
from compression import zstd
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy.engine import make_url

import grunt.backups as backups
from grunt.backups import api, tasks

SITE = "backup.test"


@pytest.fixture
def site(tmp_path, monkeypatch):
    root = tmp_path / SITE
    (root / "uploads" / "2026").mkdir(parents=True)
    (root / "uploads" / "2026" / "scan.pdf").write_bytes(b"%PDF-1.4 original")
    (root / ".env").write_text("SECRET_KEY=abc\n")
    db = root / "grunt.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("create table t (v text)")
    conn.execute("insert into t values ('original')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(backups, "site_dir", lambda s: tmp_path / s)
    monkeypatch.setattr(backups, "_db_url", lambda s: make_url(f"sqlite+aiosqlite:///{db}"))
    return root


def _rows(db) -> list[str]:
    conn = sqlite3.connect(db)
    try:
        return [r[0] for r in conn.execute("select v from t order by v")]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_backup_set_has_database_files_and_private_config(site):
    # An open writer with committed-but-not-checkpointed WAL pages: a plain
    # file copy would miss them, the backup API must not.
    writer = sqlite3.connect(site / "grunt.db")
    writer.execute("insert into t values ('in wal')")
    writer.commit()

    backup = await backups.create_backup(SITE)
    writer.close()

    assert set(backup.files) == {"database", "files", "config"}
    assert backup.files["database"].name.endswith("-database.sqlite.zst")
    assert backup.files["files"].name.endswith("-files.tar.zst")
    snapshot = site / "snapshot.sqlite"
    snapshot.write_bytes(zstd.decompress(backup.files["database"].read_bytes()))
    assert _rows(snapshot) == ["in wal", "original"]
    for path in backup.files.values():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.asyncio
async def test_backup_without_files(site):
    backup = await backups.create_backup(SITE, with_files=False)
    assert set(backup.files) == {"database", "config"}


@pytest.mark.asyncio
async def test_backup_of_chosen_parts_only(site):
    backup = await backups.create_backup(SITE, with_database=False, with_config=False)
    assert set(backup.files) == {"files"}


@pytest.mark.asyncio
async def test_backup_of_nothing_is_refused(site):
    with pytest.raises(backups.BackupError):
        await backups.create_backup(SITE, with_database=False, with_files=False, with_config=False)
    assert backups.list_backups(SITE) == []


@pytest.mark.asyncio
async def test_failed_backup_leaves_nothing_behind(site, monkeypatch):
    def boom(*_a):
        raise RuntimeError("disk full")

    monkeypatch.setattr(backups, "_backup_files", boom)
    with pytest.raises(RuntimeError):
        await backups.create_backup(SITE)
    assert backups.list_backups(SITE) == []


def test_compression_level_is_clamped():
    level = backups.zstd.CompressionParameter.compression_level
    assert backups._zstd_options(0)[level] == 1
    assert backups._zstd_options(22)[level] == backups.MAX_COMPRESSION_LEVEL


def test_rotation_keeps_the_newest(site):
    out = backups.backups_dir(SITE)
    for day in range(1, 6):
        (out / f"202609{day:02d}-020000-database.sqlite.zst").write_bytes(b"x")
    removed = backups.rotate(SITE, keep=2)
    assert removed == ["20260903-020000", "20260902-020000", "20260901-020000"]
    assert [b.id for b in backups.list_backups(SITE)] == ["20260905-020000", "20260904-020000"]


@pytest.mark.asyncio
async def test_restore_brings_back_database_and_files_and_keeps_the_old_state(site):
    backup = await backups.create_backup(SITE)
    conn = sqlite3.connect(site / "grunt.db")
    conn.execute("delete from t")
    conn.execute("insert into t values ('after backup')")
    conn.commit()
    conn.close()
    (site / "uploads" / "2026" / "scan.pdf").write_bytes(b"overwritten")

    aside = backups.restore_backup(SITE, backup, with_files=True)

    assert _rows(site / "grunt.db") == ["original"]
    assert (site / "uploads" / "2026" / "scan.pdf").read_bytes() == b"%PDF-1.4 original"
    assert _rows(aside / "grunt.db") == ["after backup"]  # undo is possible
    assert (aside / "uploads" / "2026" / "scan.pdf").read_bytes() == b"overwritten"


def test_restore_refuses_a_corrupt_copy(site):
    out = backups.backups_dir(SITE)
    (out / "20260901-020000-database.sqlite.zst").write_bytes(zstd.compress(b"not a database"))
    backup = backups.get_backup(SITE, "20260901-020000")
    with pytest.raises((backups.BackupError, sqlite3.DatabaseError)):
        backups.restore_backup(SITE, backup)
    assert _rows(site / "grunt.db") == ["original"]  # untouched


def test_backup_is_due_after_the_interval(site):
    now = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    assert tasks.is_due(SITE, 24, now)  # nothing yet
    (backups.backups_dir(SITE) / "20260923-020000-database.sqlite.zst").write_bytes(b"x")
    assert not tasks.is_due(SITE, 24, now)
    assert tasks.is_due(SITE, 24, now + timedelta(hours=14))
    assert tasks.is_due(SITE, 6, now)


@pytest.mark.asyncio
async def test_signed_download(site, client, monkeypatch):
    monkeypatch.setattr(api, "_site", lambda: SITE)
    backup = await backups.create_backup(SITE, with_files=False)
    name = backup.files["database"].name
    url = api.download_url(SITE, name)

    ok = await client.get(url)  # no token — the signature is the permission
    assert ok.status_code == 200
    assert ok.content == backup.files["database"].read_bytes()

    qs = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    forged = await client.get(api._DOWNLOAD, params={**qs, "sig": "0" * 64})
    assert forged.status_code == 403
    expired_url = api.download_url(SITE, name, now=0)
    assert (await client.get(expired_url)).status_code == 403
    traversal = api.download_url(SITE, "../.env")
    assert (await client.get(traversal)).status_code == 404


@pytest.mark.asyncio
async def test_health_reports_missing_and_fresh_backups(site, ctx, monkeypatch):
    from grunt.monitoring import health
    from grunt.site.manager import site_manager

    monkeypatch.setattr(site_manager, "get_active_site", lambda: SITE)
    rows = await health.check_backups()
    assert any(r["check"] == "Остання копія" and r["status"] == "Error" for r in rows)

    await backups.create_backup(SITE, with_files=False)
    rows = await health.check_backups()
    [last] = [r for r in rows if r["check"] == "Остання копія"]
    assert last["status"] == "OK"


@pytest.mark.asyncio
async def test_backup_progress_counts_every_byte(site):
    from grunt.progress import Progress

    progress = Progress("Backup", user=None)
    await backups.create_backup(SITE, progress=progress)
    assert progress.total > 0
    assert progress.done == progress.total


@pytest.mark.asyncio
async def test_a_backup_in_the_making_is_not_listed(site, monkeypatch):
    seen = []

    def spy(uploads, dest, level, progress):
        seen.append(dest.name)
        seen.append([b.id for b in backups.list_backups(SITE)])
        dest.write_bytes(b"archive")

    monkeypatch.setattr(backups, "_backup_files", spy)
    backup = await backups.create_backup(SITE)
    assert seen[0].startswith(".") and seen[0].endswith(".part")
    assert seen[1] == []  # the database was done, but the set wasn't complete yet
    assert set(backup.files) == {"database", "files", "config"}
    assert not list(backups.backups_dir(SITE).glob(".*"))


@pytest.mark.asyncio
async def test_disk_full_leaves_nothing_behind(site, monkeypatch):
    def full(uploads, dest, level, progress):
        dest.write_bytes(b"half")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(backups, "_backup_files", full)
    with pytest.raises(OSError):
        await backups.create_backup(SITE)
    assert list(backups.backups_dir(SITE).iterdir()) == []


def test_leftovers_of_a_killed_backup_are_removed(site):
    import os

    out = backups.backups_dir(SITE)
    old_file = out / ".20260901-020000-files.tar.zst.part"
    old_file.write_bytes(b"x")
    old_dir = out / ".tmpabc.part"
    old_dir.mkdir()
    (old_dir / "snapshot.sqlite").write_bytes(b"x")
    fresh = out / ".20260928-020000-files.tar.zst.part"  # a backup running right now
    fresh.write_bytes(b"x")
    long_ago = datetime(2026, 9, 1, tzinfo=UTC).timestamp()
    for path in (old_file, old_dir):
        os.utime(path, (long_ago, long_ago))

    backups._remove_stale_parts(out)
    assert [p.name for p in out.iterdir()] == [fresh.name]


@pytest.mark.asyncio
async def test_cancelled_backup_leaves_nothing_behind(site):
    from grunt.progress import Progress, TaskCancelledError

    progress = Progress("Backup", user=None)
    progress.cancelled = True  # as the flusher sets it after the user pressed cancel
    with pytest.raises(TaskCancelledError):
        await backups.create_backup(SITE, progress=progress)
    assert list(backups.backups_dir(SITE).iterdir()) == []


@pytest.mark.asyncio
async def test_parts_are_made_quickest_first(site, monkeypatch):
    order = []
    real_sqlite, real_files, real_copy = (
        backups._backup_sqlite,
        backups._backup_files,
        backups.shutil.copyfile,
    )

    def sqlite(*a):
        order.append("database")
        real_sqlite(*a)

    def files(*a):
        order.append("files")
        real_files(*a)

    def copy(src, dst):
        order.append("config")
        return real_copy(src, dst)

    monkeypatch.setattr(backups, "_backup_sqlite", sqlite)
    monkeypatch.setattr(backups, "_backup_files", files)
    monkeypatch.setattr(backups.shutil, "copyfile", copy)
    await backups.create_backup(SITE)
    # the test uploads are a few bytes, smaller than the database
    assert order == ["config", "files", "database"]
