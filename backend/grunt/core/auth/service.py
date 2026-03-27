"""Auth service — password hashing, JWT tokens, user CRUD via User DocType table."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import structlog
from jose import jwt
from sqlalchemy import func, select, Table
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.config import settings
from grunt.core.auth.models import GruntUser, GruntUserRole

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


# ── Table helper ─────────────────────────────────────────────────────────


def _user_table() -> Table:
    """Return the SA Core Table for the ``User`` DocType (grunt_core_user).

    Uses compile_doctype_to_table (extend_existing=True) so it works on every
    startup — same pattern as DocumentService.
    """
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    dt = doctype_registry._doctypes.get("User")
    if dt is None:
        raise RuntimeError(
            "DocType 'User' not found in registry. "
            "Ensure load_core_doctypes() ran before auth operations."
        )
    return compile_doctype_to_table(dt)


async def _load_user_roles(user_id: str, session: AsyncSession) -> list[GruntUserRole]:
    result = await session.execute(
        select(GruntUserRole).where(GruntUserRole.user_id == user_id)
    )
    return list(result.scalars().all())


def _row_to_user(row: dict, user_roles: list[GruntUserRole]) -> GruntUser:
    return GruntUser(
        id=row["id"],
        email=row["email"] or "",
        full_name=row["full_name"] or "",
        hashed_password=row["hashed_password"] or "",
        is_active=bool(row["is_active"]) if row["is_active"] is not None else True,
        is_superadmin=bool(row["is_superadmin"]) if row["is_superadmin"] is not None else False,
        created_at=row["created_at"],
        modified_at=row["modified_at"],
        user_roles=user_roles,
    )


# ── User CRUD ────────────────────────────────────────────────────────────


async def get_user_by_email(email: str, session: AsyncSession) -> GruntUser | None:
    table = _user_table()
    result = await session.execute(
        select(table).where(table.c.email == email)
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    user_roles = await _load_user_roles(row["id"], session)
    return _row_to_user(dict(row), user_roles)


async def get_user_by_id(user_id: str, session: AsyncSession) -> GruntUser | None:
    table = _user_table()
    result = await session.execute(
        select(table).where(table.c.id == user_id)
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    user_roles = await _load_user_roles(row["id"], session)
    return _row_to_user(dict(row), user_roles)


async def list_users(session: AsyncSession) -> list[GruntUser]:
    table = _user_table()
    result = await session.execute(select(table))
    rows = result.mappings().all()
    users = []
    for row in rows:
        user_roles = await _load_user_roles(row["id"], session)
        users.append(_row_to_user(dict(row), user_roles))
    return users


async def create_user(
    email: str,
    password: str,
    full_name: str,
    session: AsyncSession,
) -> GruntUser:
    """Create a new user.  The first ever user gets ``is_superadmin=True``."""
    table = _user_table()

    count_result = await session.execute(select(func.count()).select_from(table))
    user_count = count_result.scalar() or 0

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    is_superadmin = user_count == 0

    await session.execute(
        table.insert().values(
            id=user_id,
            name=email,
            owner="system",
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_active=True,
            is_superadmin=is_superadmin,
            created_at=now,
            modified_at=now,
            modified_by="system",
            docstatus=0,
        )
    )
    await session.flush()
    logger.info("auth.user_created", email=email, superadmin=is_superadmin)

    user = await get_user_by_email(email, session)
    assert user is not None
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
