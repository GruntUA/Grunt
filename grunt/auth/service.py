"""Auth service — JWT access tokens and refresh/reset token lifecycle.

User CRUD, password hashing, and authentication logic live in the
User DocType controller: ``grunt.core.doctypes.User.User``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt
import structlog

from grunt.config import settings

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

logger = structlog.get_logger()


# ── JWT ───────────────────────────────────────────────────────────────────


def create_access_token(user: User) -> str:
    """Create a JWT with user identity claims to avoid DB lookups on every request."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
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
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_mfa_token(user: User) -> str:
    """Create a short-lived token meant ONLY for MFA verification during login."""
    expire = datetime.now(UTC) + timedelta(minutes=5)
    payload = {
        "sub": user.email,
        "uid": user.id,
        "mfa_pending": True,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_mfa_token(token: str) -> dict | None:
    """Validate MFA token and return payload if valid."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if not payload.get("mfa_pending"):
            return None
        return payload
    except jwt.PyJWTError:
        return None


# ── Refresh tokens ────────────────────────────────────────────────────────


async def create_refresh_token(user_id: str) -> str:
    """Issue a 7-day refresh token for a user."""
    from grunt.app import grunt
    from grunt.context import require_session

    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    expires_at = datetime.now(UTC) + timedelta(days=7)

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

    user_data = await _find_and_invalidate_token(
        "refresh_token", "refresh_token_expires_at", token
    )
    if user_data is None:
        return None

    from grunt.app import grunt
    from grunt.auth.doctypes.User.user import get_user_by_id

    async with grunt.context(require_session()):
        user = await get_user_by_id(user_data["name"])
    if user is None:
        return None

    new_token = await create_refresh_token(user.id)
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
