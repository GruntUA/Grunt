"""Cloud storage (StorageRemote + rclone): config, file operations, backups
uploaded / rotated / fetched back, old files moved out and read through the
cache, secrets never handed out, OAuth helpers.

Runs against rclone's ``local`` backend («Server folder») - no network.
"""

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

import grunt.backups as backups
from grunt.storage import backends
from grunt.storage.cloud import MASK, mask_secrets
from grunt.storage.cloud.rclone import CRYPT, Rclone, build_config, obscure

pytestmark = pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed")

SITE = "cloud.test"
TEST_SITE = "__pytest__"  # the active site under pytest


def _remote(tmp_path, **values):
    return {
        "name": values.pop("name", "nas"),
        "title": "NAS",
        "provider": "Server folder",
        "enabled": 1,
        "root_folder": str(tmp_path / "remote"),
        **values,
    }


# Config


def test_obscure_matches_rclone_reveal():
    secret = "pa ss ї"
    out = subprocess.run(
        ["rclone", "reveal", obscure(secret)], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == secret


def test_config_obscures_secrets_and_wraps_crypt():
    config = build_config(
        {
            "provider": "SFTP",
            "host": "backup.example.com",
            "username": "grunt",
            "password": "hunter2",
            "root_folder": "/srv/grunt/",
            "encrypt": 1,
            "encryption_password": "key",
            "rclone_options": "# tuning\nmd5sum_command = none\nport = 2222",
        }
    )
    base = config["remote"]
    assert base["type"] == "sftp"
    assert base["pass"] != "hunter2" and base["pass"]
    assert base["port"] == "2222"  # rclone_options win over generated values
    assert base["md5sum_command"] == "none"
    assert "key_pem" not in base  # empty values are left out
    crypt = config[CRYPT]
    assert crypt["remote"] == "remote:srv/grunt"
    assert crypt["filename_encryption"] == "off"
    assert "password2" not in crypt


def test_oauth_provider_config_keeps_token_and_drive_scope():
    token = json.dumps({"access_token": "a", "refresh_token": "r"})
    config = build_config({"provider": "Google Drive", "oauth_token": token})
    assert config["remote"]["scope"] == "drive.file"
    assert config["remote"]["token"] == token
    assert "client_id" not in config["remote"]  # empty: rclone's own client id


# File operations


@pytest.mark.asyncio
async def test_single_file_operations(tmp_path):
    local = tmp_path / "scan.pdf"
    local.write_bytes(b"%PDF scan")
    async with Rclone(_remote(tmp_path)) as rc:
        await rc.put_file(local, "docs/scan.pdf")
        await rc.put_bytes(b"hello", "docs/hello.txt")
        assert await rc.cat("docs/hello.txt") == b"hello"
        assert await rc.cat("docs/scan.pdf", offset=5, count=4) == b"scan"
        assert sorted(e["Path"] for e in await rc.list("docs")) == ["hello.txt", "scan.pdf"]
        await rc.delete_file("docs/hello.txt")
        await rc.delete_file("docs/missing.txt")  # already gone is fine
        assert [e["Path"] for e in await rc.list("docs")] == ["scan.pdf"]
        assert await rc.list("nothing-here") == []
    assert (tmp_path / "remote" / "docs" / "scan.pdf").read_bytes() == b"%PDF scan"


@pytest.mark.asyncio
async def test_encrypted_remote_keeps_only_ciphertext(tmp_path):
    remote = _remote(tmp_path, encrypt=1, encryption_password="s3cret")
    async with Rclone(remote) as rc:
        await rc.put_bytes(b"top secret contents", "a/note.txt")
        assert await rc.cat("a/note.txt") == b"top secret contents"
        assert [e["Path"] for e in await rc.list("a")] == ["note.txt"]
    stored = list((tmp_path / "remote" / "a").iterdir())
    assert [p.name for p in stored] == ["note.txt.bin"]  # names readable, contents not
    assert b"top secret" not in stored[0].read_bytes()


@pytest.mark.asyncio
async def test_failure_raises_remote_error(tmp_path):
    from grunt.storage.cloud import RemoteError

    async with Rclone(_remote(tmp_path)) as rc:
        with pytest.raises(RemoteError):
            await rc.cat("no/such/file")


# Backups


@pytest.fixture
def site(tmp_path, monkeypatch):
    root = tmp_path / SITE
    root.mkdir()
    monkeypatch.setattr(backups, "site_dir", lambda s: tmp_path / s)
    return root


def _fake_set(site_root, backup_id: str) -> backups.BackupSet:
    out = site_root / "backups"
    out.mkdir(exist_ok=True)
    (out / f"{backup_id}-database.sqlite.zst").write_bytes(b"db " + backup_id.encode())
    (out / f"{backup_id}-config.env").write_text("SECRET_KEY=x\n")
    backup = backups.get_backup(SITE, backup_id)
    assert backup is not None
    return backup


@pytest.mark.asyncio
async def test_backup_upload_rotation_and_fetch_back(site, tmp_path):
    from grunt.storage.cloud.backups import (
        fetch_backup,
        list_remote_backups,
        load_state,
        upload_backup,
    )

    remote = _remote(tmp_path, backup_keep=2)
    ids = ["20261001-020000", "20261002-020000", "20261003-020000"]
    for backup_id in ids:
        await upload_backup(SITE, _fake_set(site, backup_id), remote)

    remote_dir = tmp_path / "remote" / "backups" / SITE
    assert sorted(p.name[:15] for p in remote_dir.iterdir()) == sorted(ids[1:] * 2)
    state = load_state(SITE)
    assert set(state) == set(ids[1:])  # the rotated-out set is no longer marked
    assert set(state[ids[2]]) == {"nas"}

    backups.delete_backup(SITE, ids[1])
    async with Rclone(remote) as rc:
        rows = await list_remote_backups(rc, SITE)
    assert [(r["id"], r["on_server"]) for r in rows] == [(ids[2], True), (ids[1], False)]
    assert rows[0]["kinds"] == ["config", "database"]

    fetched = await fetch_backup(SITE, remote, ids[1])
    assert fetched.files["database"].read_bytes() == b"db " + ids[1].encode()
    assert not list((site / "backups").glob(".*.part"))


@pytest.mark.asyncio
async def test_upload_to_remotes_records_failure_without_raising(ctx, site, tmp_path):
    from grunt.storage.cloud.backups import upload_to_remotes

    await ctx.new_doc("StorageRemote", {**_remote(tmp_path), "title": "nas", "use_for_backups": 1})
    await ctx.new_doc(
        "StorageRemote",
        {
            "title": "broken",
            "provider": "Other",
            "rclone_type": "nosuchbackend",
            "use_for_backups": 1,
        },
    )
    await ctx.db._session().commit()

    outcome = await upload_to_remotes(SITE, _fake_set(site, "20261005-020000"))

    assert outcome["nas"] is None
    assert outcome["broken"]
    ok = await ctx.db.get_value("StorageRemote", "nas", "*")
    assert ok["last_status"] == "OK" and ok["last_backup_id"] == "20261005-020000"
    broken = await ctx.db.get_value("StorageRemote", "broken", "*")
    assert broken["last_status"] == "Error" and broken["last_error"]


# Old files out to the storage


@pytest.fixture
def storage(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(backends, "_resolve_local_upload_dir", lambda site: str(uploads))
    return uploads


async def _old_file(ctx, content: bytes, days: int = 100, **values) -> dict:
    from grunt.storage import store

    row = await store(content, "old.txt", "text/plain", **values)
    await ctx.db.set_value(
        "File", row["name"], {"created_at": datetime.now(UTC) - timedelta(days=days)}
    )
    return row


@pytest.mark.asyncio
async def test_offload_read_through_cache_recall_and_gc(ctx, storage, tmp_path):
    from grunt.storage import read
    from grunt.storage.cloud import load_remote
    from grunt.storage.cloud.files import blob_path, cache_path, offload, recall
    from grunt.storage.gc import collect_garbage

    await ctx.new_doc(
        "StorageRemote",
        {**_remote(tmp_path), "title": "nas", "use_for_files": 1, "offload_after_days": 30},
    )
    old = await _old_file(ctx, b"old scan")
    fresh = await _old_file(ctx, b"fresh scan", days=1)
    public = await _old_file(ctx, b"site image", is_public=True)
    await ctx.db._session().commit()
    remote = await load_remote("nas")

    report = await offload(remote)

    assert report == {"files": 1, "bytes": len(b"old scan")}
    key = old["content_hash"]
    assert await ctx.db.get_value("File", old["name"], "storage_remote") == "nas"
    assert await ctx.db.get_value("File", fresh["name"], "storage_remote") is None
    assert await ctx.db.get_value("File", public["name"], "storage_remote") is None
    assert not backends.get_storage_backend().path(key).exists()
    remote_blob = tmp_path / "remote" / "files" / TEST_SITE / key[:2] / key[2:4] / key
    assert remote_blob.read_bytes() == b"old scan"
    assert (await load_remote("nas"))["offloaded_files"] == 1

    # Read: fetched into the cache once, then served from there.
    assert await read(old["name"]) == b"old scan"
    assert await blob_path(key) == cache_path(key)

    await recall(remote)
    assert backends.get_storage_backend().path(key).read_bytes() == b"old scan"
    assert await ctx.db.get_value("File", old["name"], "storage_remote") is None
    assert not remote_blob.exists()

    # A remote blob nothing points at is collected (after the grace period).
    stray = hashlib.sha256(b"stray").hexdigest()
    async with Rclone(remote) as rc:
        await rc.put_bytes(b"stray", f"files/{TEST_SITE}/{stray[:2]}/{stray[2:4]}/{stray}")
    await collect_garbage(grace_seconds=0)
    async with Rclone(remote) as rc:
        assert await rc.list(f"files/{TEST_SITE}", recursive=True) == []


@pytest.mark.asyncio
async def test_blob_shared_with_a_young_row_stays_local(ctx, storage, tmp_path):
    from grunt.storage.cloud import load_remote
    from grunt.storage.cloud.files import offload_candidates

    await ctx.new_doc(
        "StorageRemote",
        {**_remote(tmp_path), "title": "nas", "use_for_files": 1, "offload_after_days": 30},
    )
    await _old_file(ctx, b"same bytes")
    await _old_file(ctx, b"same bytes", days=1)
    await ctx.db._session().commit()
    assert await offload_candidates(await load_remote("nas")) == []


@pytest.mark.asyncio
async def test_doctype_and_size_policy(ctx, storage, tmp_path):
    from grunt.storage.cloud import load_remote
    from grunt.storage.cloud.files import offload_candidates

    await ctx.new_doc(
        "StorageRemote",
        {
            **_remote(tmp_path),
            "title": "nas",
            "use_for_files": 1,
            "offload_after_days": 30,
            "offload_min_size_kb": 1,
            "offload_doctypes": "ToDo\n",
        },
    )
    big = await _old_file(ctx, b"x" * 2048, attached_to_doctype="ToDo", attached_to_id="t1")
    await _old_file(ctx, b"y" * 2048)  # library file - not a ToDo attachment
    await _old_file(ctx, b"small", attached_to_doctype="ToDo", attached_to_id="t1")
    await ctx.db._session().commit()
    assert await offload_candidates(await load_remote("nas")) == [big["content_hash"]]


# The StorageRemote document


@pytest.mark.asyncio
async def test_secrets_are_masked_and_kept_on_save(ctx, tmp_path):
    doc = await ctx.new_doc(
        "StorageRemote",
        {"title": "s3", "provider": "S3", "access_key_id": "AK", "secret_access_key": "SK"},
    )
    data = dict(doc)
    await mask_secrets(doc=data)
    assert data["secret_access_key"] == MASK and data["access_key_id"] == "AK"

    await ctx.save_doc("StorageRemote", "s3", {"secret_access_key": MASK, "region": "eu"})
    assert await ctx.db.get_value("StorageRemote", "s3", "secret_access_key") == "SK"


@pytest.mark.asyncio
async def test_only_one_files_remote_and_location_locked_while_files_live_there(
    ctx, storage, tmp_path
):
    await ctx.new_doc(
        "StorageRemote", {**_remote(tmp_path, name="a"), "title": "a", "use_for_files": 1}
    )
    from grunt.i18n import use_language

    with use_language("en"):  # the messages below are matched in English
        with pytest.raises(Exception, match="only one storage can hold files"):
            await ctx.new_doc(
                "StorageRemote", {**_remote(tmp_path, name="b"), "title": "b", "use_for_files": 1}
            )

        row = await _old_file(ctx, b"kept remotely")
        await ctx.db.set_value("File", row["name"], {"storage_remote": "a"})
        with pytest.raises(Exception, match="return them to the server first"):
            await ctx.save_doc("StorageRemote", "a", {"root_folder": str(tmp_path / "elsewhere")})
        with pytest.raises(Exception, match="before deleting it"):
            await ctx.delete_doc("StorageRemote", "a")


@pytest.mark.asyncio
async def test_refreshed_token_is_written_back(ctx, tmp_path):
    from grunt.storage.cloud import load_remote

    await ctx.new_doc("StorageRemote", {**_remote(tmp_path), "title": "nas"})
    remote = await load_remote("nas")
    async with Rclone(remote) as rc:
        text = rc.config_path.read_text()
        rc.config_path.write_text(text.replace("type = local", 'type = local\ntoken = {"new":1}'))
    assert await ctx.db.get_value("StorageRemote", "nas", "oauth_token") == '{"new":1}'


# OAuth helpers


def test_oauth_state_round_trip_and_expiry():
    from grunt.storage.cloud.oauth import make_state, read_state

    assert read_state(make_state("drive", "a@b.c")) == ("drive", "a@b.c")
    with pytest.raises(ValueError):
        read_state(make_state("drive", "a@b.c", now=0))
    forged = make_state("drive", "a@b.c").split(".")[0] + ".00"
    with pytest.raises(ValueError):
        read_state(forged)


def test_pasted_token_and_rclone_format():
    from grunt.storage.cloud import RemoteError
    from grunt.storage.cloud.oauth import parse_pasted_token, rclone_token

    printed = (
        "Paste the following into your remote machine --->\n"
        '{"access_token":"x","token_type":"Bearer","refresh_token":"r",'
        '"expiry":"2026-10-12T10:00:00Z"}\n<---End paste'
    )
    assert parse_pasted_token(printed)["refresh_token"] == "r"
    with pytest.raises(RemoteError):
        parse_pasted_token("not a token")
    token = json.loads(rclone_token({"access_token": "a", "refresh_token": "r", "expires_in": 60}))
    assert token["token_type"] == "Bearer" and token["expiry"].endswith("Z")
