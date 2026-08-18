"""Unit tests for the File controller's whitelisted methods — second reference
migration onto `Document.objects`/typed `get_doc` after auth/doctypes/User/user.py
(see ADR 004). Not covered by test_file_permissions.py/test_file_delete.py, which
only exercise the DocType permissions and the before_delete hook."""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from grunt.storage.doctypes.File.file import get_list, upload


def _upload_file(name: str, content: bytes = b"hello world") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=name,
        headers=Headers({"content-type": "text/plain"}),
    )


@pytest.mark.asyncio
async def test_upload_returns_expected_shape(ctx):
    result = await upload(_upload_file("report.txt", b"some content"))

    assert result["filename"] == "report.txt"
    assert result["size_bytes"] == len(b"some content")
    assert result["content_type"] == "text/plain"
    assert result["id"]
    assert result["url"].endswith(f"file_id={result['id']}")


@pytest.mark.asyncio
async def test_get_list_returns_uploaded_files(ctx):
    await upload(_upload_file("a.txt"))
    await upload(_upload_file("b.txt"))

    result = await get_list(limit=50, page=1)

    names = {item["filename"] for item in result["items"]}
    assert {"a.txt", "b.txt"} <= names
    assert result["total"] >= 2


@pytest.mark.asyncio
async def test_get_list_respects_limit(ctx):
    for i in range(4):
        await upload(_upload_file(f"capped{i}.txt"))

    result = await get_list(limit=2, page=1)
    assert len(result["items"]) == 2
    assert result["total"] >= 4


@pytest.mark.asyncio
async def test_get_list_filters_by_content_type(ctx):
    await upload(_upload_file("plain.txt"))

    result = await get_list(filters={"content_type": "text/plain"})
    assert all(item["content_type"] == "text/plain" for item in result["items"])
