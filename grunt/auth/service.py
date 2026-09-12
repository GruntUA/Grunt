"""Auth service — JWT access tokens and refresh/reset token lifecycle.

User CRUD, password hashing, and authentication logic live in the
User DocType controller: ``grunt.core.doctypes.User.User``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt

from grunt.config import settings

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


# ── JWT ───────────────────────────────────────────────────────────────────

# Fallback when SystemSettings has no session_timeout value (very early boot).
_DEFAULT_REFRESH_TTL_MINUTES = 7 * 24 * 60


async def session_ttl_minutes() -> int:
    """How long access + refresh tokens live, from ``SystemSettings.session_timeout``.

    Both tokens share this TTL so that idle longer than the timeout invalidates
    the refresh token too (real logout), while an active user keeps going via
    refresh-token rotation.
    """
    from grunt.site.settings import get_setting

    minutes = await get_setting("session_timeout", settings.access_token_expire_minutes)
    try:
        return max(1, int(minutes))
    except TypeError, ValueError:
        return settings.access_token_expire_minutes


def create_access_token(
    user: User,
    expire_minutes: int | None = None,
    *,
    impersonator: User | None = None,
) -> str:
    """Create a JWT with user identity claims to avoid DB lookups on every request.

    When ``impersonator`` is given, the token authenticates as *user* but also
    carries ``imp*`` claims naming the superadmin who opened the session — so
    the UI can show a "you are viewing as …" banner and audit knows who acted.
    """
    minutes = expire_minutes if expire_minutes is not None else settings.access_token_expire_minutes
    expire = datetime.now(UTC) + timedelta(minutes=minutes)
    payload = {
        "sub": user.email,
        "uid": user.id,
        "full_name": user.full_name,
        "is_superadmin": user.is_superadmin,
        "is_active": user.is_active,
        "theme": user.theme,
        "roles": user.roles,
        "exp": expire,
    }
    if impersonator is not None:
        payload["imp"] = impersonator.id
        payload["imp_email"] = impersonator.email
        payload["imp_name"] = impersonator.full_name
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_challenge_token(purpose: str, *, ttl_minutes: int = 5, **claims: object) -> str:
    """Sign a short-lived, single-purpose token.

    Used for stateless multi-step ceremonies where the server has to remember
    something between two HTTP calls without a DB row — MFA hand-off, WebAuthn
    challenges, ... . ``purpose`` is checked on the way back in
    :func:`verify_challenge_token`, so a token minted for one flow can't be
    replayed into another.
    """
    payload: dict[str, object] = {
        **claims,
        "purpose": purpose,
        "exp": datetime.now(UTC) + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_challenge_token(token: str, purpose: str) -> dict | None:
    """Validate a :func:`create_challenge_token` token; return its claims or None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    return payload


def create_mfa_token(user: User) -> str:
    """Create a short-lived token meant ONLY for MFA verification during login."""
    return create_challenge_token(
        "mfa", ttl_minutes=5, sub=user.email, uid=user.id, mfa_pending=True
    )


def verify_mfa_token(token: str) -> dict | None:
    """Validate MFA token and return payload if valid."""
    payload = verify_challenge_token(token, "mfa")
    if not payload or not payload.get("mfa_pending"):
        return None
    return payload


# ── Refresh tokens ────────────────────────────────────────────────────────


async def create_refresh_token(user_id: str, expire_minutes: int | None = None) -> str:
    """Issue a refresh token for a user (TTL from ``SystemSettings.session_timeout``)."""
    from grunt.app import grunt
    from grunt.context import require_session

    minutes = expire_minutes if expire_minutes is not None else _DEFAULT_REFRESH_TTL_MINUTES
    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    expires_at = datetime.now(UTC) + timedelta(minutes=minutes)

    async with grunt.system_context(require_session()):
        await grunt.db.set_value("User", user_id, "refresh_token", token)
        await grunt.db.set_value("User", user_id, "refresh_token_expires_at", expires_at)

    return token


async def _find_and_invalidate_token(
    token_field: str, expires_field: str, token: str
) -> dict | None:
    """Find the User row holding *token* in *token_field*, check expiry, clear it.

    Shared by ``rotate_refresh_token``/``consume_password_reset_token`` — both
    are "look up a user by an opaque single-use token, reject if expired,
    invalidate it" against a different field pair, then do their own
    post-processing (issue a new token / set a new password).

    Returns the matched row (with at least ``"name"``), or None if the token
    doesn't exist or has expired.
    """
    from grunt.app import grunt
    from grunt.context import require_session

    now = datetime.now(UTC)

    async with grunt.system_context(require_session()):
        users = await grunt.get_list(
            "User",
            filters={token_field: token},
            fields=["name", expires_field],
            limit=1,
        )
        if not users:
            return None

        user_data = users[0]
        expires_at = user_data.get(expires_field)
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        if not expires_at or expires_at.replace(tzinfo=UTC) < now:
            return None

        await grunt.db.set_value("User", user_data["name"], token_field, None)
        await grunt.db.set_value("User", user_data["name"], expires_field, None)

    return user_data


async def rotate_refresh_token(token: str) -> tuple[str, User] | None:
    """Validate a refresh token, revoke it, and issue a new one.

    Returns (new_refresh_token, user) on success, None if invalid/expired.
    """
    from grunt.context import require_session

    user_data = await _find_and_invalidate_token("refresh_token", "refresh_token_expires_at", token)
    if user_data is None:
        return None

    from grunt.app import grunt
    from grunt.auth.doctypes.User.user import get_user_by_id

    async with grunt.context(require_session()):
        user = await get_user_by_id(user_data["name"])
    if user is None:
        return None

    new_token = await create_refresh_token(user.id, await session_ttl_minutes())
    return new_token, user


async def revoke_refresh_tokens_for_user(user_id: str) -> None:
    """Revoke all active refresh tokens for a user (e.g., on logout)."""
    from grunt.app import grunt
    from grunt.context import require_session

    async with grunt.system_context(require_session()):
        await grunt.db.set_value("User", user_id, "refresh_token", None)
        await grunt.db.set_value("User", user_id, "refresh_token_expires_at", None)


# ── Password reset tokens ─────────────────────────────────────────────────


async def create_password_reset_token(user_id: str) -> str:
    """Create a 1-hour password reset token. Invalidates prior unused tokens."""
    from grunt.app import grunt
    from grunt.context import require_session

    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    async with grunt.system_context(require_session()):
        await grunt.db.set_value("User", user_id, "reset_token", token)
        await grunt.db.set_value("User", user_id, "reset_token_expires_at", expires_at)

    return token


async def consume_password_reset_token(token: str, new_password: str) -> bool:
    """Verify token and update the user's password. Returns True on success."""
    user_data = await _find_and_invalidate_token("reset_token", "reset_token_expires_at", token)
    if user_data is None:
        return False

    from grunt.app import grunt
    from grunt.auth.doctypes.User.user import hash_password
    from grunt.context import require_session

    async with grunt.system_context(require_session()):
        await grunt.db.set_value(
            "User",
            user_data["name"],
            "hashed_password",
            await hash_password(new_password),
        )

    return True
