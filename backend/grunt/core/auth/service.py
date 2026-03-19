"""Auth service — password hashing, JWT tokens, user CRUD."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import structlog
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.config import settings
from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()


# ── Password helpers ─────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT ──────────────────────────────────────────────────────────────────


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


# ── User CRUD ────────────────────────────────────────────────────────────


async def get_user_by_email(email: str, session: AsyncSession) -> GruntUser | None:
    result = await session.execute(
        select(GruntUser).where(GruntUser.email == email)
    )
    return result.scalar_one_or_none()


async def create_user(
    email: str,
    password: str,
    full_name: str,
    session: AsyncSession,
) -> GruntUser:
    """Create a new user.  The first ever user gets ``is_superadmin=True``."""
    # Check if this is the very first user
    count_result = await session.execute(select(func.count()).select_from(GruntUser))
    user_count = count_result.scalar() or 0

    user = GruntUser(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_superadmin=(user_count == 0),
    )
    session.add(user)
    await session.flush()
    # Eagerly load the user_roles relationship so .roles works outside session
    await session.refresh(user, ["user_roles"])
    logger.info("auth.user_created", email=email, superadmin=user.is_superadmin)
    return user


async def authenticate(
    email: str,
    password: str,
    session: AsyncSession,
) -> GruntUser | None:
    """Return user if credentials are valid, else ``None``."""
    user = await get_user_by_email(email, session)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
