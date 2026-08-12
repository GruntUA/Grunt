"""Tests for grunt.storage.doctypes.File.file."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_before_delete_propagates_storage_failure():
    """Regression: deleting the physical file is a required step, not best-effort.

    before_delete used to catch any exception from the storage backend, log
    it, and return as if nothing happened — so a storage failure (permission
    error, network issue with S3, ...) let the File document row be deleted
    anyway, leaving an orphaned physical file with no record pointing to it.
    It must now propagate so delete_document aborts before the row is removed.
    """
    from grunt.storage.doctypes.File.file import File

    doc = File("File", {"name": "f1", "path": "2026/08/12/f1.pdf"})

    backend = MagicMock()
    backend.delete = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch("grunt.storage.doctypes.File.file.get_storage_backend", return_value=backend),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await doc.before_delete()

    backend.delete.assert_awaited_once_with("2026/08/12/f1.pdf")


@pytest.mark.asyncio
async def test_before_delete_noop_without_path():
    """No path stored (e.g. already cleaned up) → nothing to delete, no call."""
    from grunt.storage.doctypes.File.file import File

    doc = File("File", {"name": "f1", "path": ""})

    backend = MagicMock()
    backend.delete = AsyncMock()

    with patch("grunt.storage.doctypes.File.file.get_storage_backend", return_value=backend):
        await doc.before_delete()

    backend.delete.assert_not_awaited()
