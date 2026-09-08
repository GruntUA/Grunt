"""Tests for grunt.storage.doctypes.File.file.before_delete (ref-counted)."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from grunt.app import grunt
from grunt.storage.doctypes.File.file import File, dedupe_storage, upload


def _upload_file(name: str, content: bytes = b"hello world") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=name,
        headers=Headers({"content-type": "text/plain"}),
    )


@pytest.mark.asyncio
async def test_before_delete_propagates_storage_failure(ctx):
    """Regression: deleting the physical file is a required step, not best-effort.

    before_delete used to catch any exception from the storage backend, log
    it, and return as if nothing happened — so a storage failure let the File
    row be deleted anyway, orphaning the physical file. It must propagate so
    delete_document aborts before the row is removed.
    """
    result = await upload(_upload_file("solo.txt", b"only copy"))
    doc = await File.objects.filter(name=result["id"]).first()
    assert doc is not None

    backend = MagicMock()
    backend.delete = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch("grunt.storage.doctypes.File.file.get_storage_backend", return_value=backend),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await doc.before_delete()

    backend.delete.assert_awaited_once_with(doc.path)


@pytest.mark.asyncio
async def test_before_delete_noop_without_path():
    """No path stored (e.g. already cleaned up) → nothing to delete, no call."""
    doc = File("File", {"name": "f1", "path": ""})

    backend = MagicMock()
    backend.delete = AsyncMock()

    with patch("grunt.storage.doctypes.File.file.get_storage_backend", return_value=backend):
        await doc.before_delete()

    backend.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_before_delete_skips_storage_while_path_is_shared(ctx):
    """After de-dup two rows share one blob — deleting one must not touch disk."""
    a = await upload(_upload_file("share-a.txt", b"shared bytes"))
    b = await upload(_upload_file("share-b.txt", b"shared bytes"))
    await dedupe_storage()

    doc_b = await File.objects.filter(name=b["id"]).first()
    assert doc_b is not None
    backend = MagicMock()
    backend.delete = AsyncMock()

    with patch("grunt.storage.doctypes.File.file.get_storage_backend", return_value=backend):
        await doc_b.before_delete()

    backend.delete.assert_not_awaited()

    # And once the last sharer goes, the blob is dropped.
    with patch("grunt.storage.doctypes.File.file.get_storage_backend", return_value=backend):
        await grunt.delete_doc("File", b["id"])
    doc_a = await File.objects.filter(name=a["id"]).first()
    assert doc_a is not None
    with patch("grunt.storage.doctypes.File.file.get_storage_backend", return_value=backend):
        await doc_a.before_delete()

    backend.delete.assert_awaited_once_with(doc_a.path)
