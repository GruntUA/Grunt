"""Signed file URLs - let the browser fetch a private file without a bearer token.

``<img src>`` and plain links can't send ``Authorization``, so a
``get_content?file_id=…`` URL the API hands out gets ``&exp=…&sig=…`` appended
by :func:`sign_authorized_file_urls` (and the variants below) at each API
chokepoint - but only for the files the caller is actually allowed to read, so
echoing a file id back through a text field is not a usable link to any file.
A valid, unexpired signature is itself the permission to read that one file;
without one, :func:`grunt.storage.doctypes.File.file.get_content` falls back to
the regular per-user permission check.

The expiry is rounded up to the hour, so a URL stays byte-identical for an
hour and the browser cache keeps working.
"""

import hashlib
import hmac
import re
import time
from typing import Any

from grunt.config import settings
lazy import grunt
lazy from grunt.permissions.rbac import permission_checker

# How long a signed URL stays usable (plus up to one hour of rounding).
SIGNED_URL_TTL_SECONDS = 12 * 3600

_URL_PREFIX = "/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id="
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


# A file id inside a response *string* (JSON value or embedded HTML), not yet
# signed. Must match only our own *relative* file URL, never the same string
# riding on another host: the leading ``(?<![\w.\-/])`` means the internal
# ``/api/v1/method/...`` path is not preceded by hostname/path characters, so
# ``<img src="https://evil.example/api/v1/.../get_content?file_id=X">`` does not
# match and a valid signature is never appended onto a link to another origin.
_UNSIGNED_STR = re.compile(
    r"(?<![\w.\-/])" + re.escape(_URL_PREFIX) + r"([A-Za-z0-9_-]+)(?![A-Za-z0-9_-]|&exp=|&amp;exp=)"
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
    user_email = getattr(user, "email", None) if user is not None else None

    meta = None
    for fid in ids:
        doc = by_id.get(fid)
        if doc is None:
            continue
        # Cheap wins first - these cover the common case (public avatars /
        # website images, and a user's own attachments) with no extra query,
        # so the per-file permission check below only runs for the rest
        # (inherited / shared files), not once per row on every list response.
        if doc.get("is_public"):
            authorized.add(fid)
            continue
        if user_email is None:
            continue  # guest: only public files
        if doc.get("owner") == user_email:
            authorized.add(fid)  # File grants read to its owner
            continue

        assert user is not None  # user_email was set, so user is a real User
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


def sign_all_file_urls(data: Any) -> Any:
    """Sign every (relative, internal) file URL in *data*, unconditionally.

    Only for a payload the caller has already authorized *as a whole* - a
    token-shared document (``share.get_shared_document``), where the share token
    is the authorization for that document and its attachments, and the guest
    has no user for a per-file check. Still bounded to our own relative URLs by
    ``_UNSIGNED_STR``, so it cannot sign a link pointing at another host.
    """
    ids: set[str] = set()
    _collect_file_ids(data, ids)
    if not ids:
        return data
    return _sign_in_structure(data, ids, _expiry())


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
