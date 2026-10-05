"""Signed file URLs - let the browser fetch a private file without a bearer token.

``<img src>`` and plain links can't send ``Authorization``, so every
``get_content?file_id=…`` URL leaving the API gets ``&exp=…&sig=…`` appended
(:class:`SignedFileURLResponse`, the app's default response class). A valid,
unexpired signature is itself the permission to read that one file; without
one, :func:`grunt.storage.doctypes.File.file.get_content` falls back to the
regular per-user permission check.

The expiry is rounded up to the hour, so a URL stays byte-identical for an
hour and the browser cache keeps working.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Any

from fastapi.responses import JSONResponse

from grunt.config import settings

# How long a signed URL stays usable (plus up to one hour of rounding).
SIGNED_URL_TTL_SECONDS = 12 * 3600

_URL_PREFIX = "/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id="
_UNSIGNED = re.compile(
    re.escape(_URL_PREFIX).encode() + rb"([A-Za-z0-9_-]+)(?![A-Za-z0-9_-]|&exp=|&amp;exp=)"
)
# A signature as it comes back from the client - plain or HTML-escaped (rich text).
_SIGNATURE = re.compile(
    r"(get_content\?file_id=[A-Za-z0-9_-]+)(?:&|&amp;)exp=\d+(?:&|&amp;)sig=[0-9a-f]+"
)


def _signature(file_id: str, exp: int) -> str:
    msg = f"file:{file_id}:{exp}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()[:32]


def _expiry(now: float | None = None) -> int:
    now = time.time() if now is None else now
    return (int(now + SIGNED_URL_TTL_SECONDS) // 3600 + 1) * 3600


def verify(file_id: str, exp: int | None, sig: str | None, now: float | None = None) -> bool:
    if not exp or not sig:
        return False
    if exp < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(sig, _signature(file_id, exp))


def sign_file_urls(body: bytes) -> bytes:
    """Append a signature to every unsigned file-content URL in *body*."""
    if b"get_content?file_id=" not in body:
        return body
    exp = _expiry()
    return _UNSIGNED.sub(
        lambda m: m.group(0) + f"&exp={exp}&sig={_signature(m.group(1).decode(), exp)}".encode(),
        body,
    )


def strip_file_signatures(value: Any) -> Any:
    """Remove signatures from file URLs in data being saved (strings, dicts, lists).

    Signed URLs are handed to the client for display; if one is saved back into
    a document (an Attach field, an image in rich text) it must be stored bare,
    or it would stop working once the signature expires.
    """
    if isinstance(value, str):
        return _SIGNATURE.sub(r"\1", value) if "sig=" in value else value
    if isinstance(value, dict):
        return {k: strip_file_signatures(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_file_signatures(v) for v in value]
    return value


def sign_file_urls_in_html(html: str) -> str:
    """:func:`sign_file_urls` for server-rendered HTML (print formats)."""
    return sign_file_urls(html.encode()).decode()


class SignedFileURLResponse(JSONResponse):
    """JSONResponse that signs the file URLs it carries (see module doc)."""

    def render(self, content: Any) -> bytes:
        return sign_file_urls(super().render(content))
