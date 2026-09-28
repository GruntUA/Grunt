"""UserSession — one row per signed-in device, holding that device's refresh token.

The row name is the session id (``sid``) carried in every access token, so a
token can be traced back to its device. The refresh token itself is stored
only as a SHA-256 hash and is rotated on every refresh.

A session ends when it is revoked (logout, "sign out other devices", password
reset) or after ``SystemSettings.session_timeout`` minutes without a refresh —
an idle timeout, not an absolute one: an active client keeps refreshing its
short-lived access token and each refresh moves ``last_active_at`` forward.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import grunt
from grunt.i18n import _

if TYPE_CHECKING:
    from fastapi import Request


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def client_ip(request: Request | None) -> str | None:
    """The caller's real IP behind Cloudflare / a reverse proxy.

    Forwarded-IP headers are honoured only when the connection itself comes
    from ``settings.trusted_proxies`` (any of them) or, with
    ``settings.trust_cloudflare``, from a Cloudflare edge (CF-Connecting-IP
    only); otherwise they could be forged.
    """
    from grunt.auth.ip_policy import CLOUDFLARE_RANGES, ip_allowed
    from grunt.config import settings

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


async def _deactivate_expired(user_id: str, ttl_minutes: int) -> None:
    """Close the user's sessions that went idle past the timeout."""
    cutoff = datetime.now(UTC) - timedelta(minutes=ttl_minutes)
    rows = await grunt.db.get_all(
        "UserSession",
        filters={"user": user_id, "is_active": True},
        fields=["name", "last_active_at"],
    )
    for row in rows:
        last = _as_utc(row.get("last_active_at"))
        if last is None or last < cutoff:
            await grunt.db.set_value("UserSession", row["name"], "is_active", False)


async def open_session(
    user_id: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """Start a session for a successful login. Returns ``(sid, refresh_token)``."""
    from grunt.auth.service import session_ttl_minutes
    from grunt.local import require_session

    sid = uuid.uuid4().hex
    refresh_token = secrets.token_hex(32)

    async with grunt.system_context(require_session()):
        await _deactivate_expired(user_id, await session_ttl_minutes())
        await grunt.new_doc(
            "UserSession",
            {
                "name": sid,
                "user": user_id,
                "refresh_token_hash": _hash(refresh_token),
                "ip_address": ip_address or "",
                "user_agent": (user_agent or "")[:512],
                "last_active_at": datetime.now(UTC),
                "is_active": True,
            },
        )
    return sid, refresh_token


async def rotate_session(
    refresh_token: str,
    ip_address: str | None,
) -> tuple[str, str, str] | None:
    """Swap a refresh token for a new one. Returns ``(sid, refresh_token, user_id)``.

    None when the token is unknown, revoked, or its session went idle past
    ``session_timeout``. An idle session isn't closed here — the caller turns
    None into an error, which rolls the request back; ``_deactivate_expired``
    closes it on the next login or session listing.
    """
    from grunt.auth.service import session_ttl_minutes
    from grunt.local import require_session

    async with grunt.system_context(require_session()):
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
    from grunt.local import require_session

    async with grunt.system_context(require_session()):
        await grunt.db.set_value("UserSession", sid, "is_active", False)


async def end_all_sessions(user_id: str, keep_sid: str | None = None) -> int:
    """Revoke every active session of a user, optionally sparing ``keep_sid``."""
    from grunt.local import require_session

    async with grunt.system_context(require_session()):
        rows = await grunt.db.get_all(
            "UserSession",
            filters={"user": user_id, "is_active": True},
            fields=["name"],
        )
        ended = [row["name"] for row in rows if row["name"] != keep_sid]
        for sid in ended:
            await grunt.db.set_value("UserSession", sid, "is_active", False)
    return len(ended)


@grunt.whitelist()
async def list_my_sessions() -> list[dict[str, Any]]:
    """Active sessions of the current user; ``current`` marks this device."""
    from grunt.auth.service import session_ttl_minutes
    from grunt.local import require_session

    current = await grunt.get_current_user()
    assert current.id is not None
    async with grunt.system_context(require_session()):
        await _deactivate_expired(current.id, await session_ttl_minutes())
        rows = await grunt.db.get_all(
            "UserSession",
            filters={"user": current.id, "is_active": True},
            fields=["name", "ip_address", "user_agent", "last_active_at", "created_at"],
            order_by="last_active_at",
            order="desc",
        )
    sid = current.data.get("_sid")
    return [{**row, "current": row["name"] == sid} for row in rows]


@grunt.whitelist()
async def revoke_my_session(session_id: str) -> bool:
    """Sign out one of the current user's devices."""
    from grunt.local import require_session

    current = await grunt.get_current_user()
    async with grunt.system_context(require_session()):
        owner = await grunt.db.get_value("UserSession", session_id, "user")
    if owner is None or owner != current.id:
        grunt.throw(_("Session not found"), "NOT_FOUND")
    await end_session(session_id)
    return True


@grunt.whitelist()
async def revoke_other_sessions() -> int:
    """Sign out every device of the current user except this one."""
    current = await grunt.get_current_user()
    assert current.id is not None
    return await end_all_sessions(current.id, keep_sid=current.data.get("_sid"))
