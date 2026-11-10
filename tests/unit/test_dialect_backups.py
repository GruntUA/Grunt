"""Dialect dump / restore: credentials, failures and a restore that can't finish."""

import re
import shutil
import sqlite3
import subprocess
from compression import zstd
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from grunt.db.dialects import PostgresDialect, SqliteDialect
from grunt.db.dialects.archive import BackupError
from grunt.i18n import _
from grunt.progress import Progress

PG_URL = make_url("postgresql+asyncpg://grunt:s3cret@db.local:5432/site")


@pytest.fixture
def pg_tools(monkeypatch):
    calls: list[dict] = []
    outcome = {"returncode": 0, "stderr": ""}

    def run(args, **kwargs):
        calls.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args, outcome["returncode"], "", outcome["stderr"])

    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(subprocess, "run", run)
    return calls, outcome


def test_postgres_password_never_reaches_the_arguments(pg_tools, tmp_path):
    calls, _ = pg_tools
    PostgresDialect().dump(PG_URL, tmp_path / "x.pgdump", 9, Progress("", user=None))
    PostgresDialect().restore_dump(PG_URL, tmp_path / "x.pgdump", tmp_path)

    for call in calls:
        assert not any("s3cret" in str(arg) for arg in call["args"])
        assert call["env"]["PGPASSWORD"] == "s3cret"
        assert call["args"][-1] == "postgresql://grunt@db.local:5432/site"


def test_postgres_client_failure_is_a_backup_error(pg_tools, tmp_path):
    _, outcome = pg_tools
    outcome.update(returncode=1, stderr="pg_dump: error: connection refused\n")
    with pytest.raises(BackupError, match="connection refused"):
        PostgresDialect().dump(PG_URL, tmp_path / "x.pgdump", 9, Progress("", user=None))


def test_postgres_restore_keeps_the_current_database_aside(pg_tools, tmp_path):
    calls, _ = pg_tools
    PostgresDialect().restore_dump(PG_URL, tmp_path / "x.pgdump", tmp_path)

    (dump, restore) = (call["args"] for call in calls)
    assert dump[0] == "pg_dump" and str(tmp_path / "database.pgdump") in dump
    assert restore[0] == "pg_restore" and "--single-transaction" in restore


def test_postgres_restore_stops_when_the_aside_dump_fails(pg_tools, tmp_path):
    calls, outcome = pg_tools
    outcome.update(returncode=1, stderr="pg_dump: error: disk full\n")
    with pytest.raises(BackupError, match="disk full"):
        PostgresDialect().restore_dump(PG_URL, tmp_path / "x.pgdump", tmp_path)
    assert [call["args"][0] for call in calls] == ["pg_dump"]


def test_postgres_missing_client_is_a_backup_error(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    message = _("%(tool)s not found; install the PostgreSQL client") % {"tool": "pg_dump"}
    with pytest.raises(BackupError, match=re.escape(message)):
        PostgresDialect().restore_dump(PG_URL, tmp_path / "x.pgdump", tmp_path)


def _sqlite_site(tmp_path: Path) -> tuple[Path, Path]:
    db = tmp_path / "grunt.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('live')")
    conn.close()
    dump = tmp_path / "set.sqlite.zst"
    with zstd.open(dump, "wb") as out:
        out.write(db.read_bytes())
    return db, dump


def test_sqlite_corrupt_archive_is_a_backup_error(tmp_path):
    db, _ = _sqlite_site(tmp_path)
    broken = tmp_path / "broken.sqlite.zst"
    broken.write_bytes(b"not zstd at all")
    aside = tmp_path / "aside"
    aside.mkdir()
    with pytest.raises(BackupError):
        SqliteDialect().restore_dump(make_url(f"sqlite:///{db}"), broken, aside)
    assert db.exists()


def test_sqlite_failed_swap_puts_the_live_database_back(tmp_path, monkeypatch):
    db, dump = _sqlite_site(tmp_path)
    aside = tmp_path / "aside"
    aside.mkdir()
    real_move = shutil.move

    def move(src, dst):
        if Path(src).name == "restored.sqlite":
            raise OSError("disk full")
        return real_move(src, dst)

    monkeypatch.setattr(shutil, "move", move)
    message = _("The restore failed, the database was left as it was: %(error)s")
    with pytest.raises(BackupError, match=re.escape(message % {"error": "disk full"})):
        SqliteDialect().restore_dump(make_url(f"sqlite:///{db}"), dump, aside)

    assert db.exists() and not (aside / "grunt.db").exists()
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT v FROM t").fetchone() == ("live",)


def test_postgres_client_gets_libpq_parameters_only(pg_tools, tmp_path):
    calls, _ = pg_tools
    url = make_url(
        "postgresql+asyncpg://grunt:s3cret@db.local/site"
        "?ssl=require&prepared_statement_cache_size=0&application_name=grunt"
    )
    PostgresDialect().dump(url, tmp_path / "x.pgdump", 9, Progress("", user=None))
    conninfo = make_url(calls[0]["args"][-1])
    # ssl (asyncpg) -> sslmode (libpq); driver-only options dropped
    assert dict(conninfo.query) == {"sslmode": "require", "application_name": "grunt"}
