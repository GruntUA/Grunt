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

import httpx2

from grunt import _
from grunt.storage import files
from grunt.storage.backends import get_storage_backend

_MAX_REDIRECTS = 5
_TIMEOUT = httpx2.Timeout(30.0, connect=10.0)
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
    blob = await files.compress_stored(key, size, name, content_type)
    return await files.create_file(
        blob.key,
        blob.size,
        blob.filename,
        blob.content_type,
        folder=folder,
        original_size=blob.original_size,
    )


async def _download(url: str, buffer: Any, limit: int) -> tuple[httpx2.Headers, str]:
    async with httpx2.AsyncClient(follow_redirects=False, timeout=_TIMEOUT) as client:
        for _hop in range(_MAX_REDIRECTS + 1):
            # Resolve + validate, then connect to *that* IP. Re-resolving inside
            # the HTTP client (as a plain GET url would) reopens a DNS-rebinding
            # SSRF: the check sees a public IP, the connection a private one. The
            # Host header and TLS SNI stay the real hostname so vhosts and cert
            # verification still work.
            ip = await _check_public(url)
            parts = urlsplit(url)
            # Host header is hostname[:port] only - never the userinfo that may
            # sit in netloc (``user:pass@host``), which would leak credentials
            # in a header and make servers reject the request.
            host_header = parts.hostname or ""
            if parts.port:
                host_header = f"{host_header}:{parts.port}"
            ip_host = f"[{ip}]" if ":" in ip else ip
            connect_url = parts._replace(
                netloc=f"{ip_host}:{parts.port}" if parts.port else ip_host
            ).geturl()
            headers = {"Host": host_header}
            extensions = {"sni_hostname": parts.hostname} if parts.scheme == "https" else {}
            # Credentials in the URL (``user:pass@``) are dropped from the IP
            # connect URL - carry them as Basic auth instead, so an authenticated
            # link still works.
            auth = (
                (unquote(parts.username or ""), unquote(parts.password or ""))
                if parts.username
                else None
            )
            async with client.stream(
                "GET", connect_url, headers=headers, extensions=extensions, auth=auth
            ) as response:
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


async def _check_public(url: str) -> str:
    """Validate *url* and return one resolved, public IP to connect to.

    Every address the host resolves to must be global; the returned IP is the
    one the caller must connect to (so the connection can't be re-resolved to a
    private address between check and connect - DNS rebinding).
    """
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
    chosen: str | None = None
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise RemoteFileError(_("Links to internal network addresses are not allowed"))
        if chosen is None:
            chosen = str(address)
    if chosen is None:
        raise RemoteFileError(_("The site “%(host)s” was not found") % {"host": parts.hostname})
    return chosen


def _filename(disposition: str | None, url: str) -> str:
    match = _FILENAME.search(disposition or "")
    name = unquote(match.group(1)) if match else unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    return name.strip().replace("/", "_")[:200] or "download"
