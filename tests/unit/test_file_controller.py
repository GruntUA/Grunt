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


@pytest.mark.asyncio
async def test_get_list_search_matches_file_name_case_insensitively(ctx):
    await upload(_upload_file("Quarterly-Report.txt"))
    await upload(_upload_file("random-notes.txt"))

    result = await get_list(search="quarterly")

    names = {item["filename"] for item in result["items"]}
    assert names == {"Quarterly-Report.txt"}


@pytest.mark.asyncio
async def test_get_list_search_combines_with_filters(ctx):
    await upload(_upload_file("scoped-doc.txt"), attached_to_doctype="Letter", attached_to_id="L-1")
    await upload(_upload_file("scoped-doc.txt"))  # same name, not attached

    result = await get_list(
        search="scoped-doc",
        filters={"attached_to_doctype": "Letter", "attached_to_id": "L-1"},
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["filename"] == "scoped-doc.txt"


@pytest.mark.asyncio
async def test_get_list_blank_search_is_ignored(ctx):
    await upload(_upload_file("visible.txt"))

    result = await get_list(search="   ")
    assert result["total"] >= 1


@pytest.mark.asyncio
async def test_upload_deduplicates_identical_reupload(ctx):
    first = await upload(_upload_file("dup.txt", b"identical bytes"))
    second = await upload(_upload_file("dup.txt", b"identical bytes"))

    assert first["deduped"] is False
    assert second["deduped"] is True
    assert second["id"] == first["id"]

    listed = await get_list(search="dup.txt")
    assert len([i for i in listed["items"] if i["name"] == first["id"]]) == 1


@pytest.mark.asyncio
async def test_upload_dedup_requires_matching_name(ctx):
    a = await upload(_upload_file("a-name.txt", b"same bytes here"))
    b = await upload(_upload_file("b-name.txt", b"same bytes here"))

    assert b["deduped"] is False
    assert b["id"] != a["id"]


@pytest.mark.asyncio
async def test_upload_dedup_is_scoped_to_attachment_target(ctx):
    a = await upload(
        _upload_file("shared.txt", b"same"),
        attached_to_doctype="Letter",
        attached_to_id="L-1",
    )
    b = await upload(
        _upload_file("shared.txt", b"same"),
        attached_to_doctype="Letter",
        attached_to_id="L-2",
    )

    assert b["deduped"] is False
    assert b["id"] != a["id"]


@pytest.mark.asyncio
async def test_upload_dedup_distinguishes_different_content(ctx):
    a = await upload(_upload_file("notes.txt", b"version one"))
    b = await upload(_upload_file("notes.txt", b"version two"))

    assert b["deduped"] is False
    assert b["id"] != a["id"]
