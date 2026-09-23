"""File previews: WebP thumbnails for images and PDFs, made at upload and served
through the same signed get_content URL."""

from __future__ import annotations

import io
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image

from grunt.storage.thumbnails import THUMB_WIDTH, make_thumbnail


def _png(w: int = 1600, h: int = 900) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 40, 40)).save(buf, "PNG")
    return buf.getvalue()


def _pdf() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1240, 1754), (255, 255, 255)).save(buf, "PDF")
    return buf.getvalue()


def _size(webp: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(webp)) as img:
        assert img.format == "WEBP"
        return img.size


@pytest.mark.asyncio
async def test_image_thumbnail_is_small_webp():
    thumb = await make_thumbnail(_png(), "image/png")
    assert thumb is not None
    assert _size(thumb)[0] == THUMB_WIDTH


@pytest.mark.asyncio
async def test_pdf_first_page_thumbnail():
    thumb = await make_thumbnail(_pdf(), "application/pdf")
    assert thumb is not None
    w, h = _size(thumb)
    assert w == THUMB_WIDTH and h > w  # portrait A4 page


@pytest.mark.asyncio
async def test_unsupported_or_broken_files_get_no_thumbnail():
    assert await make_thumbnail(b"plain text", "text/plain") is None
    assert await make_thumbnail(b"%PDF-1.4 garbage", "application/pdf") is None


@pytest.mark.asyncio
async def test_uploaded_pdf_serves_signed_thumbnail(client, auth_headers):
    M = "/api/v1/method/grunt.storage.doctypes.File.file"
    up = await client.post(
        f"{M}.upload",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"attached_to_doctype": "User", "attached_to_id": "admin@grunt.example.com"},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    thumb_url = up.json()["data"]["thumbnail_url"]
    assert "&thumb=1" in thumb_url and "&sig=" in thumb_url

    # Private attachment, no token — the signature alone opens the preview.
    r = await client.get(thumb_url)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert _size(r.content)[0] == THUMB_WIDTH

    file_id = parse_qs(urlparse(thumb_url).query)["file_id"][0]
    listed = await client.get(f"{M}.get_list", params={"search": "scan"}, headers=auth_headers)
    [item] = [i for i in listed.json()["data"]["items"] if i["name"] == file_id]
    assert "&thumb=1" in item["thumbnail_url"]
