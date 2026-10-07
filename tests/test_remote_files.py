"""«Create → From a link»: the server downloads only public http(s) addresses,
follows redirects with the same check, and files the download like an upload."""

from __future__ import annotations

import httpx2
import pytest

from grunt.storage import backends, remote


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_resolve_local_upload_dir", lambda site: str(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/a.pdf",
        "http://127.0.0.1/a.pdf",
        "http://localhost:8000/api",
        "http://10.0.0.5/a.pdf",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/a.pdf",
    ],
)
async def test_internal_and_odd_links_are_refused(url):
    with pytest.raises(remote.RemoteFileError):
        await remote._check_public(url)


def test_filename_from_disposition_or_path():
    assert (
        remote._filename('attachment; filename="Рішення 1.docx"', "https://x/y") == "Рішення 1.docx"
    )
    assert remote._filename("attachment; filename*=UTF-8''%D0%90.pdf", "https://x/y") == "А.pdf"
    assert remote._filename(None, "https://x/files/%D0%91.doc?v=1") == "Б.doc"
    assert remote._filename(None, "https://x/") == "download"


def _mock_client(monkeypatch, handler):
    real = httpx2.AsyncClient

    def factory(**kwargs):
        return real(transport=httpx2.MockTransport(handler), **kwargs)

    monkeypatch.setattr(remote.httpx2, "AsyncClient", factory)

    async def public(url):
        if "internal" in url:
            raise remote.RemoteFileError("internal")

    monkeypatch.setattr(remote, "_check_public", public)


@pytest.mark.asyncio
async def test_download_follows_redirects_and_guesses_type_by_name(ctx, storage, monkeypatch):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/go":
            return httpx2.Response(302, headers={"location": "/files/decision.docx"})
        return httpx2.Response(
            200, content=b"PK docx bytes", headers={"content-type": "application/octet-stream"}
        )

    _mock_client(monkeypatch, handler)
    row = await remote.fetch_file("https://example.com/go")
    assert row["file_name"] == "decision.docx"
    assert row["content_type"].endswith("wordprocessingml.document")
    assert row["file_size"] == len(b"PK docx bytes")


@pytest.mark.asyncio
async def test_redirect_to_an_internal_address_is_refused(ctx, storage, monkeypatch):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"location": "http://internal/secret"})

    _mock_client(monkeypatch, handler)
    with pytest.raises(remote.RemoteFileError):
        await remote.fetch_file("https://example.com/go")


@pytest.mark.asyncio
async def test_too_large_download_is_refused(ctx, storage, monkeypatch):
    monkeypatch.setattr(remote.files, "upload_limit", lambda: 10)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"x" * 100, headers={"content-type": "text/plain"})

    _mock_client(monkeypatch, handler)
    with pytest.raises(remote.RemoteFileError):
        await remote.fetch_file("https://example.com/big.txt")
