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
    """Append a signature to every unsigned file-content URL in *body*.

    Unconditional: signs any file id present. Only safe where the payload was
    built under an authorization the whole of it inherits (a token-shared
    document, a server-authored print/website template). For API responses
    carrying arbitrary user content use :func:`sign_authorized_file_urls`,
    which signs only the files the current user may actually read - otherwise
    any field that echoes input back becomes a signing oracle for *any* file.
    """
    if b"get_content?file_id=" not in body:
        return body
    exp = _expiry()
    return _UNSIGNED.sub(
        lambda m: m.group(0) + f"&exp={exp}&sig={_signature(m.group(1).decode(), exp)}".encode(),
        body,
    )


# A file id inside a response *string* (JSON value or embedded HTML), not yet
# signed. Mirrors `_UNSIGNED`'s "not already signed" lookahead.
_UNSIGNED_STR = re.compile(
    r"get_content\?file_id=([A-Za-z0-9_-]+)(?![A-Za-z0-9_-]|&exp=|&amp;exp=)"
)


def _collect_file_ids(data: Any, out: set[str]) -> None:
    if isinstance(data, str):
        if "get_content?file_id=" in data:
            out.update(m.group(1) for m in _UNSIGNED_STR.finditer(data))
    elif isinstance(data, dict):
        for v in data.values():
            _collect_file_ids(v, out)
    elif isinstance(data, (list, tuple)):
        for v in data:
            _collect_file_ids(v, out)


def _sign_str(text: str, authorized: set[str], exp: int) -> str:
    if "get_content?file_id=" not in text:
        return text

    def repl(m: Any) -> str:
        fid = m.group(1)
        if fid not in authorized:
            return m.group(0)  # not readable by this user -> leave unsigned
        return m.group(0) + f"&exp={exp}&sig={_signature(fid, exp)}"

    return _UNSIGNED_STR.sub(repl, text)


def _sign_value(v: Any, authorized: set[str], exp: int) -> Any:
    """Return *v* with authorized file URLs in it signed (strings/tuples are
    rebuilt since they are immutable; dicts/lists are mutated in place)."""
    if isinstance(v, str):
        return _sign_str(v, authorized, exp) if "get_content?file_id=" in v else v
    if isinstance(v, tuple):
        return tuple(_sign_value(x, authorized, exp) for x in v)
    if isinstance(v, (dict, list)):
        return _sign_in_structure(v, authorized, exp)
    return v


def _sign_in_structure(data: Any, authorized: set[str], exp: int) -> Any:
    """Append signatures to authorized file URLs, mutating containers in place.

    Dicts and lists are edited in place (only string/tuple leaves are replaced),
    so the original container types - ``AttrDict`` rows, a ``DocumentList`` -
    and any non-URL values are preserved and not deep-copied. Immutable leaves
    (``str``, ``tuple``) are rebuilt and reassigned into their parent.
    """
    if isinstance(data, str):
        return _sign_str(data, authorized, exp)
    if isinstance(data, tuple):
        return tuple(_sign_value(x, authorized, exp) for x in data)
    if isinstance(data, dict):
        for k, v in data.items():
            data[k] = _sign_value(v, authorized, exp)
        return data
    if isinstance(data, list):
        for i, v in enumerate(data):
            data[i] = _sign_value(v, authorized, exp)
        return data
    return data


async def _authorized_file_ids(ids: set[str], user: Any) -> set[str]:
    """Of *ids*, those the current *user* may actually read.

    A public file is readable by anyone (guests included). A private file is
    signed only for an authenticated user who passes the File read check - the
    same check ``get_content`` falls back to - so ``match`` rules, inherited
    access (attachment / folder) and shares all apply. No user -> only public.
    """
    import grunt

    authorized: set[str] = set()
    rows = await grunt.db.get_all(
        "File",
        filters={"name__in": list(ids)},
        fields=[
            "name",
            "owner",
            "is_public",
            "attached_to_doctype",
            "attached_to_id",
            "folder",
        ],
        limit=None,
    )
    by_id = {str(r["name"]): r for r in rows}

    meta = None
    for fid in ids:
        doc = by_id.get(fid)
        if doc is None:
            continue
        if doc.get("is_public"):
            authorized.add(fid)
            continue
        if user is None or not getattr(user, "id", None):
            continue
        from grunt.permissions.rbac import permission_checker

        if meta is None:
            meta = await grunt.get_meta("File")
        if meta is not None and await permission_checker.check(user, meta, "read", doc):
            authorized.add(fid)
    return authorized


async def sign_authorized_file_urls(data: Any, user: Any) -> Any:
    """Sign file URLs in *data*, but only for files *user* may read.

    Replaces the blanket response-wide signing: walks the response structure,
    finds unsigned ``get_content`` URLs, resolves which files the user is
    actually authorized to read, and appends a signature only to those. A file
    id the user cannot read is left bare - fetching it then falls back to the
    per-user permission check in ``get_content`` (401/403), so echoing a file
    id back through a text field no longer mints a usable link.
    """
    ids: set[str] = set()
    _collect_file_ids(data, ids)
    if not ids:
        return data
    authorized = await _authorized_file_ids(ids, user)
    if not authorized:
        return data
    return _sign_in_structure(data, authorized, _expiry())


async def sign_authorized_file_urls_in_text(text: str, user: Any) -> str:
    """:func:`sign_authorized_file_urls` for a single string (HTML / JSON text).

    For server-rendered HTML (print, export) and MCP text payloads: signs only
    the file ids *user* may read, leaving the rest bare.
    """
    if "get_content?file_id=" not in text:
        return text
    ids: set[str] = set()
    _collect_file_ids(text, ids)
    if not ids:
        return text
    authorized = await _authorized_file_ids(ids, user)
    if not authorized:
        return text
    return _sign_in_structure(text, authorized, _expiry())


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
