"""Content-addressed file storage: blobs keyed by SHA-256, shared by File rows,
freed by the garbage collector (grunt.storage.backends / files / gc)."""

from __future__ import annotations

import hashlib
import io
import os
import time

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

import grunt
from grunt.storage import backends
from grunt.storage.backends import FileTooLargeError, LocalStorageBackend
from grunt.storage.doctypes.File.file import get_content, remove, upload
from grunt.storage.gc import collect_garbage, verify


@pytest.fixture
def storage(tmp_path, monkeypatch) -> LocalStorageBackend:
    """A fresh uploads dir for the test site."""
    monkeypatch.setattr(backends, "_resolve_local_upload_dir", lambda site: str(tmp_path))
    backend = backends.get_storage_backend()
    assert isinstance(backend, LocalStorageBackend)
    return backend


def _upload_file(name: str, content: bytes) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content), filename=name, headers=Headers({"content-type": "text/plain"})
    )


def _age(path, seconds: int = 7200) -> None:
    past = time.time() - seconds
    os.utime(path, (past, past))


async def _key(file_id: str) -> str:
    return await grunt.db.get_value("File", file_id, "content_hash")


# ── backend ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_names_blob_by_sha256_in_sharded_dir(storage):
    key, size = await storage.put(b"payload")

    assert key == hashlib.sha256(b"payload").hexdigest()
    assert size == 7
    assert storage.path(key) == storage.root / "blobs" / key[:2] / key[2:4] / key
    assert await storage.get(key) == b"payload"
    assert not any((storage.root / "tmp").iterdir())


@pytest.mark.asyncio
async def test_put_streams_and_enforces_size_limit(storage):
    with pytest.raises(FileTooLargeError):
        await storage.put(io.BytesIO(b"x" * 100), max_bytes=10)
    # Nothing half-written is left behind.
    assert not (storage.root / "blobs").exists()
    assert not any((storage.root / "tmp").iterdir())


@pytest.mark.asyncio
async def test_put_of_known_content_keeps_one_copy_and_refreshes_mtime(storage):
    key, _ = await storage.put(b"same")
    _age(storage.path(key))
    await storage.put(b"same")

    assert [k for k, _ in storage.iter_keys()] == [key]
    assert storage.path(key).stat().st_mtime > time.time() - 60


@pytest.mark.asyncio
async def test_keys_that_are_not_hashes_never_become_paths(storage):
    with pytest.raises(FileNotFoundError):
        await storage.get("../../grunt.db")


# ── File rows ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_identical_bytes_under_different_names_share_one_blob(ctx, storage):
    a = await upload(_upload_file("first.txt", b"shared payload"))
    b = await upload(_upload_file("second.txt", b"shared payload"))

    assert a["id"] != b["id"]
    assert await _key(a["id"]) == await _key(b["id"])
    assert len(list(storage.iter_keys())) == 1


@pytest.mark.asyncio
async def test_upload_over_limit_is_413_and_stores_nothing(ctx, storage, monkeypatch):
    from grunt.config import settings

    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    with pytest.raises(HTTPException) as exc:
        await upload(_upload_file("big.txt", b"more than zero bytes"))
    assert exc.value.status_code == 413
    assert list(storage.iter_keys()) == []


@pytest.mark.asyncio
async def test_disallowed_type_is_415(ctx, storage):
    bad = UploadFile(
        file=io.BytesIO(b"MZ"),
        filename="x.exe",
        headers=Headers({"content-type": "application/x-msdownload"}),
    )
    with pytest.raises(HTTPException) as exc:
        await upload(bad)
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_store_creates_private_file_with_url(ctx, storage):
    doc = await grunt.storage.store(b"a,b\n1,2\n", "export.csv", "text/csv")

    assert doc["file_url"].endswith(f"file_id={doc['name']}")
    assert doc["content_hash"] == hashlib.sha256(b"a,b\n1,2\n").hexdigest()
    assert not doc["is_public"]
    assert await grunt.storage.read(doc["name"]) == b"a,b\n1,2\n"


@pytest.mark.asyncio
async def test_get_content_streams_with_etag(ctx, storage):
    up = await upload(_upload_file("notes.txt", b"hello"))

    response = await get_content(up["id"])

    assert response.path == storage.path(await _key(up["id"]))
    assert response.headers["etag"] == f'"{await _key(up["id"])}"'
    assert "attachment" in response.headers["content-disposition"]


# ── garbage collection ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gc_keeps_a_blob_while_another_row_shares_it(ctx, storage):
    a = await upload(_upload_file("keep-a.txt", b"linked content"))
    b = await upload(_upload_file("keep-b.txt", b"linked content"))
    key = await _key(a["id"])
    _age(storage.path(key))

    await remove(b["id"])
    await _purge_trash()
    report = await collect_garbage()

    assert report["freed_blobs"] == 0
    assert (await get_content(a["id"])).status_code == 200


@pytest.mark.asyncio
async def test_gc_frees_blob_once_no_row_nor_trash_refers_to_it(ctx, storage):
    up = await upload(_upload_file("gone.txt", b"to be collected"))
    key = await _key(up["id"])
    _age(storage.path(key))

    await remove(up["id"])
    trashed = await grunt.db.count("DeletedDocument", {"deleted_doctype": "File"})
    if trashed:
        # A trashed File may be restored — its blob must survive.
        assert (await collect_garbage())["freed_blobs"] == 0
        assert storage.path(key).exists()
        await _purge_trash()

    report = await collect_garbage()
    assert report["freed_blobs"] == 1
    assert not storage.path(key).exists()


@pytest.mark.asyncio
async def test_gc_spares_young_blobs(ctx, storage):
    key, _ = await storage.put(b"just uploaded, row not written yet")

    assert (await collect_garbage())["freed_blobs"] == 0
    assert storage.path(key).exists()


@pytest.mark.asyncio
async def test_gc_sweeps_abandoned_uploads(ctx, storage):
    tmp = storage.root / "tmp"
    tmp.mkdir(parents=True)
    stale = tmp / "abandoned"
    stale.write_bytes(b"partial")
    _age(stale)

    assert (await collect_garbage())["tmp_removed"] == 1
    assert not stale.exists()


@pytest.mark.asyncio
async def test_verify_reports_missing_and_unreferenced(ctx, storage):
    up = await upload(_upload_file("lost.txt", b"lost blob"))
    storage.path(await _key(up["id"])).unlink()
    stray, _ = await storage.put(b"no row")

    report = await verify(rehash=True)

    assert report["missing"] == [up["id"]]
    assert report["unreferenced"] == [stray]
    assert report["corrupt"] == []


async def _purge_trash() -> None:
    await grunt.db.delete("DeletedDocument", {"deleted_doctype": "File"})


@pytest.mark.asyncio
async def test_download_supports_range_and_etag_over_http(client, auth_headers, storage):
    m = "/api/v1/method/grunt.storage.doctypes.File.file"
    up = await client.post(
        f"{m}.upload",
        files={"file": ("digits.txt", b"0123456789", "text/plain")},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    url = up.json()["data"]["url"]

    part = await client.get(url, headers={**auth_headers, "Range": "bytes=2-5"})
    assert part.status_code == 206
    assert part.content == b"2345"

    full = await client.get(url, headers=auth_headers)
    assert full.content == b"0123456789"
    again = await client.get(url, headers={**auth_headers, "If-None-Match": full.headers["etag"]})
    assert again.status_code == 304


# ── folders ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_list_navigates_by_folder_tree(ctx):
    meta = await grunt.get_meta("File")
    assert meta is not None and meta.list_tree_field == "folder"
    folder_meta = await grunt.get_meta("FileFolder")
    assert folder_meta is not None and folder_meta.is_tree


@pytest.mark.asyncio
async def test_upload_into_folder_and_move_without_touching_disk(ctx, storage):
    reports = (await grunt.new_doc("FileFolder", {"folder_name": "Reports"}))["name"]
    archive = (await grunt.new_doc("FileFolder", {"folder_name": "Archive"}))["name"]

    up = await upload(_upload_file("q3.txt", b"quarter three"), folder=reports)
    assert await grunt.db.get_value("File", up["id"], "folder") == reports

    blob = storage.path(await _key(up["id"]))
    mtime = blob.stat().st_mtime
    await grunt.save_doc("File", up["id"], {"folder": archive})

    assert await grunt.db.get_value("File", up["id"], "folder") == archive
    assert blob.stat().st_mtime == mtime


@pytest.mark.asyncio
async def test_same_file_in_two_folders_is_two_rows(ctx, storage):
    a = (await grunt.new_doc("FileFolder", {"folder_name": "A"}))["name"]
    b = (await grunt.new_doc("FileFolder", {"folder_name": "B"}))["name"]

    first = await upload(_upload_file("logo.txt", b"logo"), folder=a)
    second = await upload(_upload_file("logo.txt", b"logo"), folder=b)

    assert first["id"] != second["id"]
    assert len(list(storage.iter_keys())) == 1


@pytest.mark.asyncio
async def test_only_an_empty_folder_can_be_deleted(ctx, storage):
    parent = (await grunt.new_doc("FileFolder", {"folder_name": "Parent"}))["name"]
    child = (await grunt.new_doc("FileFolder", {"folder_name": "Child", "parent_folder": parent}))[
        "name"
    ]
    up = await upload(_upload_file("inside.txt", b"inside"), folder=child)

    with pytest.raises(HTTPException) as has_files:
        await grunt.delete_doc("FileFolder", child)
    assert has_files.value.status_code == 422
    with pytest.raises(HTTPException) as has_subfolders:
        await grunt.delete_doc("FileFolder", parent)
    assert has_subfolders.value.status_code == 422

    await remove(up["id"])
    await grunt.delete_doc("FileFolder", child)
    await grunt.delete_doc("FileFolder", parent)
