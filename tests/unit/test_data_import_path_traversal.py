"""Regression: path traversal / arbitrary local file read via
DataImport._resolve_file_path().

`self.file` is a plain string field on DataImport (fieldtype "Attach"),
fully controlled by whoever creates the document (anyone with `create` on
DataImport — System Manager only, but that role has no other framework
mechanism for reading arbitrary local files; ServerScript's sandbox, for
instance, specifically blocks file I/O). The old implementation did
`Path(self.file); if path.exists(): return path` *before* attempting to
resolve `self.file` as a real uploaded File reference — so
`{"file": "/etc/passwd"}` (or any other server-local path readable by the
app process, e.g. a `.env` with SECRET_KEY) would be "imported" and its
contents surfaced back through get_preview()'s headers/rows.
"""

from __future__ import annotations

import pytest

from grunt.io.doctypes.DataImport.data_import import DataImport


def _make_data_import(file_value: str) -> DataImport:
    return DataImport("DataImport", {"name": "test-import", "file": file_value})


@pytest.mark.asyncio
async def test_raw_local_path_is_not_resolved(tmp_path):
    """A local filesystem path that happens to exist must not be treated as
    a valid import source, even though it "exists" on disk.
    """
    secret_file = tmp_path / "secret.csv"
    secret_file.write_text("SECRET_KEY,value\nprod,hunter2\n")

    doc = _make_data_import(str(secret_file))
    with pytest.raises(FileNotFoundError):
        await doc._resolve_file_path()


@pytest.mark.asyncio
async def test_etc_passwd_style_path_is_not_resolved():
    doc = _make_data_import("/etc/passwd")
    with pytest.raises(FileNotFoundError):
        await doc._resolve_file_path()


@pytest.mark.asyncio
async def test_relative_traversal_path_is_not_resolved():
    doc = _make_data_import("../../../../etc/passwd")
    with pytest.raises(FileNotFoundError):
        await doc._resolve_file_path()
