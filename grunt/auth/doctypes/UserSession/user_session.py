"""UserSession - one row per signed-in device, holding that device's refresh token.

The row name is the session id (``sid``) carried in every access token, so a
token can be traced back to its device. The refresh token itself is stored
only as a SHA-256 hash and is rotated on every refresh.

A device is a browser profile: the SPA keeps a random id in the
``grunt_device`` cookie. Signing in again from the same browser reuses its row
(new refresh token, same ``sid``) and appends to ``logins``, the last
``SystemSettings.session_login_history`` sign-ins. Without the cookie every
sign-in opens a row of its own.

A session ends when it is revoked (logout, "sign out other devices", password
reset) or after ``SystemSettings.session_timeout`` minutes without a refresh -
an idle timeout, not an absolute one: an active client keeps refreshing its
short-lived access token and each refresh moves ``last_active_at`` forward.
"""

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from starlette.requests import HTTPConnection

import grunt
from grunt import _
from grunt.auth.ip_policy import CLOUDFLARE_RANGES, ip_allowed
from grunt.auth.service import session_ttl_minutes
from grunt.config import settings
from grunt.document.base import Document
from grunt.site.settings import get_setting

DEVICE_COOKIE = "grunt_device"
_DEVICE_ID = re.compile(r"[0-9a-f]{32}")
DEFAULT_LOGIN_HISTORY = 20


class UserSession(Document):
    """DocType controller for UserSession."""

    # "user" field: read it as self.data["user"] - self.user is the session user.
    refresh_token_hash: str | None
    device_id: str | None
    ip_address: str | None
    user_agent: str | None
    last_active_at: datetime | None
    is_active: bool | None
    logins: list[dict[str, Any]]  # Table: UserSessionLogin


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def client_ip(request: HTTPConnection | None) -> str | None:
    """The caller's real IP behind Cloudflare / a reverse proxy.

    Forwarded-IP headers are honoured only when the connection itself comes
    from ``settings.trusted_proxies`` (any of them) or, with
    ``settings.trust_cloudflare``, from a Cloudflare edge (CF-Connecting-IP
    only); otherwise they could be forged.
    """
    if request is None:
        return None
    peer = request.client.host if request.client else None
    headers = request.headers
    if peer and not ip_allowed(peer, set(settings.trusted_proxies)):
        cf_ip = (headers.get("cf-connecting-ip") or "").strip()
        if cf_ip and settings.trust_cloudflare and ip_allowed(peer, set(CLOUDFLARE_RANGES)):
            return cf_ip
        return peer
    ip = headers.get("cf-connecting-ip") or headers.get("x-real-ip")
    if not ip and (forwarded := headers.get("x-forwarded-for")):
        ip = forwarded.split(",")[0]
    ip = (ip or "").strip() or peer
    return ip or None


def client_user_agent(request: Request | None) -> str | None:
    return request.headers.get("user-agent") if request is not None else None


def client_device_id(request: HTTPConnection | None) -> str | None:
    """The browser's ``grunt_device`` cookie, if it looks like one."""
    value = request.cookies.get(DEVICE_COOKIE) if request is not None else None
    return value if value and _DEVICE_ID.fullmatch(value) else None


async def deactivate_expired(user_id: str | None, ttl_minutes: int) -> int:
    """Close sessions (of one user, or everyone's) that went idle past the timeout."""
    cutoff = datetime.now(UTC) - timedelta(minutes=ttl_minutes)
    filters: dict[str, Any] = {"is_active": True}
    if user_id is not None:
        filters["user"] = user_id
    rows = await grunt.db.get_all(
        "UserSession", filters=filters, fields=["name", "last_active_at"], limit=None
    )
    closed = 0
    for row in rows:
        last = _as_utc(row.get("last_active_at"))
        if last is None or last < cutoff:
            await grunt.db.set_value("UserSession", row["name"], "is_active", False)
            closed += 1
    return closed


async def open_session(
    user_id: str,
    ip_address: str | None,
    user_agent: str | None,
    *,
    device_id: str | None = None,
    method: str | None = None,
) -> tuple[str, str]:
    """Start a session for a successful login. Returns ``(sid, refresh_token)``.

    A known ``device_id`` of this user takes over that device's row instead
    of opening a new one; the old refresh token stops working.
    """
    refresh_token = secrets.token_hex(32)
    now = datetime.now(UTC)
    user_agent = (user_agent or "")[:512]
    values: dict[str, Any] = {
        "refresh_token_hash": _hash(refresh_token),
        "ip_address": ip_address or "",
        "user_agent": user_agent,
        "last_active_at": now,
        "is_active": True,
    }
    login = {
        "login_at": now,
        "ip_address": ip_address or "",
        "user_agent": user_agent,
        "method": method or "",
    }

    async with grunt.system_context(grunt.get_session()):
        await deactivate_expired(user_id, await session_ttl_minutes())
        rows = []
        if device_id:
            rows = await grunt.db.get_all(
                "UserSession",
                filters={"user": user_id, "device_id": device_id},
                fields=["name"],
                order_by="last_active_at",
                order="desc",
                limit=1,
            )
        if not rows:
            sid = uuid.uuid4().hex
            await grunt.new_doc(
                "UserSession",
                {
                    "name": sid,
                    "user": user_id,
                    "device_id": device_id or "",
                    **values,
                    "logins": [login],
                },
            )
            return sid, refresh_token

        sid = rows[0]["name"]
        keep = await get_setting("session_login_history", DEFAULT_LOGIN_HISTORY)
        doc = await grunt.get_doc(UserSession, sid)
        logins = [{key: row.get(key) for key in login} for row in doc.logins or []]
        logins = [*logins, login][-max(int(keep or 1), 1) :]
        await grunt.save_doc("UserSession", sid, {**values, "logins": logins})
    return sid, refresh_token


async def rotate_session(
    refresh_token: str,
    ip_address: str | None,
) -> tuple[str, str, str] | None:
    """Swap a refresh token for a new one. Returns ``(sid, refresh_token, user_id)``.

    None when the token is unknown, revoked, or its session went idle past
    ``session_timeout``. An idle session isn't closed here - the caller turns
    None into an error, which rolls the request back; ``deactivate_expired``
    closes it on the next login or session listing.
    """
    async with grunt.system_context(grunt.get_session()):
        rows = await grunt.db.get_all(
            "UserSession",
            filters={"refresh_token_hash": _hash(refresh_token), "is_active": True},
            fields=["name", "user", "last_active_at"],
            limit=1,
        )
        if not rows:
            return None

        sid = rows[0]["name"]
        now = datetime.now(UTC)
        last = _as_utc(rows[0].get("last_active_at"))
        if last is None or last + timedelta(minutes=await session_ttl_minutes()) < now:
            return None

        new_token = secrets.token_hex(32)
        values: dict[str, Any] = {"refresh_token_hash": _hash(new_token), "last_active_at": now}
        if ip_address:
            values["ip_address"] = ip_address
        await grunt.db.set_value("UserSession", sid, values)
    return sid, new_token, rows[0]["user"]


async def end_session(sid: str) -> None:
    """Revoke one session (its refresh token stops working)."""

    async with grunt.system_context(grunt.get_session()):
        await grunt.db.set_value("UserSession", sid, "is_active", False)


async def end_all_sessions(user_id: str, keep_sid: str | None = None) -> int:
    """Revoke every active session of a user, optionally sparing ``keep_sid``."""

    async with grunt.system_context(grunt.get_session()):
        rows = await grunt.db.get_all(
            "UserSession",
            filters={"user": user_id, "is_active": True},
            fields=["name"],
            limit=None,
        )
        ended = [row["name"] for row in rows if row["name"] != keep_sid]
        for sid in ended:
            await grunt.db.set_value("UserSession", sid, "is_active", False)
    return len(ended)


@grunt.whitelist()
async def list_my_sessions() -> list[dict[str, Any]]:
    """Active sessions of the current user; ``current`` marks this device."""
    current = grunt.get_user()
    assert current.id is not None
    async with grunt.system_context(grunt.get_session()):
        await deactivate_expired(current.id, await session_ttl_minutes())
        rows = await grunt.db.get_all(
            "UserSession",
            filters={"user": current.id, "is_active": True},
            fields=["name", "ip_address", "user_agent", "last_active_at", "created_at"],
            order_by="last_active_at",
            order="desc",
            limit=None,
        )
    sid = current.data.get("_sid")
    return [{**row, "current": row["name"] == sid} for row in rows]


@grunt.whitelist()
async def revoke_my_session(session_id: str) -> bool:
    """Sign out one of the current user's devices."""

    current = grunt.get_user()
    async with grunt.system_context(grunt.get_session()):
        owner = await grunt.db.get_value("UserSession", session_id, "user")
    if owner is None or owner != current.id:
        grunt.throw(_("Session not found"), "NOT_FOUND")
    await end_session(session_id)
    return True


@grunt.whitelist()
async def revoke_other_sessions() -> int:
    """Sign out every device of the current user except this one."""
    current = grunt.get_user()
    assert current.id is not None
    return await end_all_sessions(current.id, keep_sid=current.data.get("_sid"))
