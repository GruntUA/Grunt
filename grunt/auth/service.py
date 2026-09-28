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

# Access tokens are short-lived; the device's UserSession (refreshed through
# its refresh token) is what carries the login across the idle timeout.
ACCESS_TOKEN_MAX_MINUTES = 15


async def session_ttl_minutes() -> int:
    """Idle timeout of a UserSession, from ``SystemSettings.session_timeout``."""
    from grunt.site.settings import get_setting

    minutes = await get_setting("session_timeout", settings.access_token_expire_minutes)
    try:
        return max(1, int(minutes))
    except TypeError, ValueError:
        return settings.access_token_expire_minutes


async def access_token_minutes() -> int:
    """Access-token TTL: short, and never longer than the session idle timeout."""
    return min(ACCESS_TOKEN_MAX_MINUTES, await session_ttl_minutes())


def create_access_token(
    user: User,
    expire_minutes: int | None = None,
    *,
    sid: str | None = None,
    impersonator: User | None = None,
) -> str:
    """Create a JWT with user identity claims to avoid DB lookups on every request.

    When ``impersonator`` is given, the token authenticates as *user* but also
    carries ``imp*`` claims naming the System Manager who opened the session —
    so the UI can show a "you are viewing as …" banner and audit knows who acted.
    """
    minutes = expire_minutes if expire_minutes is not None else settings.access_token_expire_minutes
    expire = datetime.now(UTC) + timedelta(minutes=minutes)
    payload = {
        "sub": user.email,
        "uid": user.id,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "theme": user.theme,
        "roles": user.roles,
        "exp": expire,
    }
    if sid is not None:
        payload["sid"] = sid
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


def create_mfa_setup_token(user: User) -> str:
    """Token that lets a user whose role requires MFA enroll it during login.

    A separate purpose from :func:`create_mfa_token`, so an MFA *verification*
    token can never be replayed into enrollment (or vice versa). Longer TTL —
    the user may still have to install an authenticator app.
    """
    return create_challenge_token("mfa_setup", ttl_minutes=15, sub=user.email, uid=user.id)


def verify_mfa_setup_token(token: str) -> dict | None:
    """Validate an MFA-setup token and return its claims, or None."""
    return verify_challenge_token(token, "mfa_setup")


# ── Password reset tokens ─────────────────────────────────────────────────


async def _find_and_invalidate_token(
    token_field: str, expires_field: str, token: str
) -> dict | None:
    """Find the User row holding *token* in *token_field*, check expiry, clear it.

    Used by ``consume_password_reset_token``: "look up a user by an opaque
    single-use token, reject if expired, invalidate it".

    Returns the matched row (with at least ``"name"``), or None if the token
    doesn't exist or has expired.
    """
    import grunt

    now = datetime.now(UTC)

    async with grunt.system_context(grunt.get_session()):
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


async def create_password_reset_token(user_id: str) -> str:
    """Create a 1-hour password reset token. Invalidates prior unused tokens."""
    import grunt

    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    async with grunt.system_context(grunt.get_session()):
        await grunt.db.set_value("User", user_id, "reset_token", token)
        await grunt.db.set_value("User", user_id, "reset_token_expires_at", expires_at)

    return token


async def consume_password_reset_token(token: str, new_password: str) -> bool:
    """Verify token and update the user's password. Returns True on success."""
    user_data = await _find_and_invalidate_token("reset_token", "reset_token_expires_at", token)
    if user_data is None:
        return False

    import grunt
    from grunt.auth.doctypes.User.user import hash_password

    async with grunt.system_context(grunt.get_session()):
        await grunt.db.set_value(
            "User",
            user_data["name"],
            "hashed_password",
            await hash_password(new_password),
        )

    # A password reset may be a response to a stolen account — sign out everywhere.
    from grunt.auth.doctypes.UserSession.user_session import end_all_sessions

    await end_all_sessions(user_data["name"])
    return True
