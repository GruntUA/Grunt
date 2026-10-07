"""Download a file from the internet into the storage («Create → From a link»).

The server fetches what a user names, so the address is checked first: only
http(s), and every IP the host resolves to must be a public one - no
localhost, LAN, link-local or cloud metadata addresses. Redirects are followed
by hand (at most five), each hop checked the same way. The body is streamed
into a temporary file up to the upload limit, then stored like an upload.
"""

from __future__ import annotations

import asyncio
import ipaddress
import mimetypes
import re
import socket
import tempfile
from typing import Any, BinaryIO, cast
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from grunt import _
from grunt.storage import files
from grunt.storage.backends import get_storage_backend

_MAX_REDIRECTS = 5
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_FILENAME = re.compile(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", re.IGNORECASE)


class RemoteFileError(ValueError):
    """The link can't be downloaded - the message is for the user."""


async def fetch_file(url: str, *, folder: str | None = None) -> dict[str, Any]:
    """Download *url* into the storage as a new File (in *folder*); return the row."""
    limit = files.upload_limit()
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as buffer:
        response_headers, final_url = await _download(url, buffer, limit)
        buffer.seek(0)
        name = _filename(response_headers.get("content-disposition"), final_url)
        content_type = (response_headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type in ("", "application/octet-stream", "binary/octet-stream"):
            # Servers often send documents as a bare byte stream - go by the name.
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        try:
            files.validate_mime_type(content_type)
        except ValueError as exc:
            raise RemoteFileError(str(exc)) from exc
        key, size = await get_storage_backend().put(cast("BinaryIO", buffer), max_bytes=limit)
    return await files.create_file(key, size, name, content_type, folder=folder)


async def _download(url: str, buffer: Any, limit: int) -> tuple[httpx.Headers, str]:
    async with httpx.AsyncClient(follow_redirects=False, timeout=_TIMEOUT) as client:
        for _hop in range(_MAX_REDIRECTS + 1):
            await _check_public(url)
            async with client.stream("GET", url) as response:
                if response.is_redirect and "location" in response.headers:
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.status_code >= 400:
                    raise RemoteFileError(
                        _("The link answered with an error (%(code)s)")
                        % {"code": response.status_code}
                    )
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise RemoteFileError(
                            _("The file is too large (max %(size)s MB)")
                            % {"size": limit // (1024 * 1024)}
                        )
                    buffer.write(chunk)
                return response.headers, url
    raise RemoteFileError(_("Too many redirects"))


async def _check_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RemoteFileError(_("Only http:// and https:// links can be downloaded"))
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname,
            parts.port or (443 if parts.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise RemoteFileError(
            _("The site “%(host)s” was not found") % {"host": parts.hostname}
        ) from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise RemoteFileError(_("Links to internal network addresses are not allowed"))


def _filename(disposition: str | None, url: str) -> str:
    match = _FILENAME.search(disposition or "")
    name = unquote(match.group(1)) if match else unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    return name.strip().replace("/", "_")[:200] or "download"
