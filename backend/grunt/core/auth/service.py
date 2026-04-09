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
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.core.doctypes.user.user import GruntUser

logger = structlog.get_logger()


# ── JWT ───────────────────────────────────────────────────────────────────


def create_access_token(user: GruntUser) -> str:
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


# ── Refresh tokens ────────────────────────────────────────────────────────


async def create_refresh_token(user_id: str, session: AsyncSession) -> str:
    """Issue a 7-day refresh token for a user."""
    from grunt.app import grunt
    from grunt.core.doctypes.user.user import SYSTEM_USER

    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    expires_at = datetime.now(UTC) + timedelta(days=7)

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        await grunt.db.set_value("User", user_id, "refresh_token", token)
        await grunt.db.set_value("User", user_id, "refresh_token_expires_at", expires_at)
    finally:
        grunt.reset_context(_tokens)

    return token


async def rotate_refresh_token(
    token: str,
    session: AsyncSession,
) -> tuple[str, GruntUser] | None:
    """Validate a refresh token, revoke it, and issue a new one.

    Returns (new_refresh_token, user) on success, None if invalid/expired.
    """
    from grunt.app import grunt
    from grunt.core.doctypes.user.user import SYSTEM_USER, get_user_by_id

    now = datetime.now(UTC)

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        users = await grunt.get_list(
            "User",
            filters={"refresh_token": token},
            fields=["id", "refresh_token_expires_at"],
            limit=1,
        )
        if not users:
            return None

        user_data = users[0]
        expires_at = user_data.get("refresh_token_expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        if not expires_at or expires_at.replace(tzinfo=UTC) < now:
            return None

        # Revoke token
        await grunt.db.set_value("User", user_data["id"], "refresh_token", None)
        await grunt.db.set_value("User", user_data["id"], "refresh_token_expires_at", None)

        user_id = user_data["id"]
    finally:
        grunt.reset_context(_tokens)

    user = await get_user_by_id(user_id, session)
    if user is None:
        return None

    new_token = await create_refresh_token(user.id, session)
    return new_token, user


async def revoke_refresh_tokens_for_user(user_id: str, session: AsyncSession) -> None:
    """Revoke all active refresh tokens for a user (e.g., on logout)."""
    from grunt.app import grunt
    from grunt.core.doctypes.user.user import SYSTEM_USER

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        await grunt.db.set_value("User", user_id, "refresh_token", None)
        await grunt.db.set_value("User", user_id, "refresh_token_expires_at", None)
    finally:
        grunt.reset_context(_tokens)


# ── Password reset tokens ─────────────────────────────────────────────────


async def create_password_reset_token(
    user_id: str,
    session: AsyncSession,
) -> str:
    """Create a 1-hour password reset token. Invalidates prior unused tokens."""
    from grunt.app import grunt
    from grunt.core.doctypes.user.user import SYSTEM_USER

    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        await grunt.db.set_value("User", user_id, "reset_token", token)
        await grunt.db.set_value("User", user_id, "reset_token_expires_at", expires_at)
    finally:
        grunt.reset_context(_tokens)

    return token


async def consume_password_reset_token(
    token: str,
    new_password: str,
    session: AsyncSession,
) -> bool:
    """Verify token and update the user's password. Returns True on success."""
    from grunt.app import grunt
    from grunt.core.doctypes.user.user import SYSTEM_USER, hash_password
    from grunt.core.site.manager import site_manager

    now = datetime.now(UTC)

    _engine = site_manager.get_engine(site_manager.get_active_site())
    _tokens = grunt.set_context(session, _engine, SYSTEM_USER)
    try:
        users = await grunt.get_list(
            "User",
            filters={"reset_token": token},
            fields=["id", "reset_token_expires_at"],
            limit=1,
        )
        if not users:
            return False

        user_data = users[0]
        expires_at = user_data.get("reset_token_expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        if not expires_at or expires_at.replace(tzinfo=UTC) < now:
            return False

        # Invalidate token
        await grunt.db.set_value("User", user_data["id"], "reset_token", None)
        await grunt.db.set_value("User", user_data["id"], "reset_token_expires_at", None)

        # Update password
        await grunt.db.set_value(
            "User",
            user_data["id"],
            "hashed_password",
            hash_password(new_password),
        )
    finally:
        grunt.reset_context(_tokens)

    return True
