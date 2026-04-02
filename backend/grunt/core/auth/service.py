"""Auth service — JWT access tokens and refresh/reset token lifecycle.

User CRUD, password hashing, and authentication logic live in the
User DocType controller: ``grunt.core.doctypes.User.User``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.config import settings
from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()


# ── JWT ───────────────────────────────────────────────────────────────────


def create_access_token(user: GruntUser) -> str:
    """Create a JWT containing sub=email, roles=[], exp."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": user.email,
        "roles": user.roles,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


# ── Refresh tokens ────────────────────────────────────────────────────────


async def create_refresh_token(user_id: str, session: AsyncSession) -> str:
    """Issue a 7-day refresh token for a user."""
    from grunt.core.db.system_tables import GruntRefreshToken  # noqa: PLC0415

    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    session.add(GruntRefreshToken(user_id=user_id, token=token, expires_at=expires_at))
    await session.flush()
    return token


async def rotate_refresh_token(
    token: str,
    session: AsyncSession,
) -> tuple[str, GruntUser] | None:
    """Validate a refresh token, revoke it, and issue a new one.

    Returns (new_refresh_token, user) on success, None if invalid/expired.
    """
    from grunt.core.db.system_tables import GruntRefreshToken  # noqa: PLC0415
    from grunt.core.doctypes.User.User import get_user_by_id  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(GruntRefreshToken)
        .where(GruntRefreshToken.token == token)
        .where(GruntRefreshToken.revoked.is_(False))
        .where(GruntRefreshToken.expires_at > now)
    )
    rt = result.scalar_one_or_none()
    if rt is None:
        return None

    rt.revoked = True
    await session.flush()

    user = await get_user_by_id(rt.user_id, session)
    if user is None:
        return None

    new_token = await create_refresh_token(user.id, session)
    return new_token, user


async def revoke_refresh_tokens_for_user(user_id: str, session: AsyncSession) -> None:
    """Revoke all active refresh tokens for a user (e.g., on logout)."""
    from grunt.core.db.system_tables import GruntRefreshToken  # noqa: PLC0415
    from sqlalchemy import update as sa_update  # noqa: PLC0415

    await session.execute(
        sa_update(GruntRefreshToken)
        .where(GruntRefreshToken.user_id == user_id)
        .where(GruntRefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    await session.flush()


# ── Password reset tokens ─────────────────────────────────────────────────


async def create_password_reset_token(
    user_id: str,
    session: AsyncSession,
) -> str:
    """Create a 1-hour password reset token. Invalidates prior unused tokens."""
    from grunt.core.db.system_tables import GruntPasswordResetToken  # noqa: PLC0415
    from sqlalchemy import update as sa_update  # noqa: PLC0415

    await session.execute(
        sa_update(GruntPasswordResetToken)
        .where(GruntPasswordResetToken.user_id == user_id)
        .where(GruntPasswordResetToken.used.is_(False))
        .values(used=True)
    )

    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    session.add(
        GruntPasswordResetToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
        )
    )
    await session.flush()
    return token


async def consume_password_reset_token(
    token: str,
    new_password: str,
    session: AsyncSession,
) -> bool:
    """Verify token and update the user's password. Returns True on success."""
    from grunt.core.db.system_tables import GruntPasswordResetToken  # noqa: PLC0415
    from grunt.core.doctypes.User.User import hash_password, _user_table  # noqa: PLC0415
    from sqlalchemy import update as sa_update  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(GruntPasswordResetToken)
        .where(GruntPasswordResetToken.token == token)
        .where(GruntPasswordResetToken.used.is_(False))
        .where(GruntPasswordResetToken.expires_at > now)
    )
    reset_token = result.scalar_one_or_none()
    if reset_token is None:
        return False

    reset_token.used = True
    await session.flush()

    table = _user_table()
    await session.execute(
        sa_update(table)
        .where(table.c.id == reset_token.user_id)
        .values(hashed_password=hash_password(new_password))
    )
    await session.flush()
    return True
