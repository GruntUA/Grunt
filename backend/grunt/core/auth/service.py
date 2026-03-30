"""Auth service — password hashing, JWT tokens, user CRUD via User DocType table."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import structlog
import jwt
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


def _get_doctype_from_registry(name: str):
    """Internal helper to retrieve a DocType by name without exposing registry internals.

    This isolates direct access to doctype_registry internals so it can be
    easily updated if a public accessor is added in the future.
    """
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    # NOTE: Once doctype_registry exposes a public accessor (e.g. get_doctype),
    # this function should be updated to delegate to that instead of touching
    # _doctypes directly.
    return doctype_registry._doctypes.get(name)


def _user_table() -> Table:
    """Return the SA Core Table for the ``User`` DocType (grunt_core_user).

    Uses compile_doctype_to_table (extend_existing=True) so it works on every
    startup — same pattern as DocumentService.
    """
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

    dt = _get_doctype_from_registry("User")
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
        theme=row.get("theme") or "system",
        login_attempts=int(row["login_attempts"]) if row.get("login_attempts") is not None else 0,
        locked_until=row.get("locked_until"),
        mfa_enabled=bool(row["mfa_enabled"]) if row.get("mfa_enabled") is not None else False,
        mfa_secret=row.get("mfa_secret") or "",
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

    # Revoke old token
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


async def create_password_reset_token(
    user_id: str,
    session: AsyncSession,
) -> str:
    """Create a 1-hour password reset token. Invalidates prior unused tokens."""
    from grunt.core.db.system_tables import GruntPasswordResetToken  # noqa: PLC0415

    # Invalidate existing unused tokens for this user
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

    # Mark token as used
    reset_token.used = True
    await session.flush()

    # Update password
    table = _user_table()
    await session.execute(
        sa_update(table)
        .where(table.c.id == reset_token.user_id)
        .values(hashed_password=hash_password(new_password))
    )
    await session.flush()
    return True


_MAX_ATTEMPTS = 10
_LOCKOUT_MINUTES = 30


async def authenticate(
    email: str,
    password: str,
    session: AsyncSession,
) -> GruntUser | None:
    """Return user if credentials are valid, else ``None``.

    Tracks failed attempts and locks the account after _MAX_ATTEMPTS failures.
    Raises ``ValueError("locked")`` when the account is temporarily locked.
    """
    from sqlalchemy import update as sa_update  # noqa: PLC0415

    user = await get_user_by_email(email, session)
    if user is None:
        return None

    now = datetime.now(timezone.utc)

    # Check if account is locked
    if user.locked_until:
        # Normalize locked_until to UTC for a safe comparison with `now`
        if user.locked_until.tzinfo is not None and user.locked_until.utcoffset() is not None:
            locked_until_utc = user.locked_until.astimezone(timezone.utc)
        else:
            # Treat naive datetimes as UTC
            locked_until_utc = user.locked_until.replace(tzinfo=timezone.utc)
        if locked_until_utc > now:
            raise ValueError("locked")

    if not verify_password(password, user.hashed_password):
        # Increment failed attempt counter
        new_attempts = (user.login_attempts or 0) + 1
        values: dict = {"login_attempts": new_attempts}
        if new_attempts >= _MAX_ATTEMPTS:
            values["locked_until"] = now + timedelta(minutes=_LOCKOUT_MINUTES)
            values["login_attempts"] = 0  # reset counter after locking
        table = _user_table()
        await session.execute(
            sa_update(table).where(table.c.id == user.id).values(**values)
        )
        await session.flush()
        return None

    # Successful login — reset counters
    table = _user_table()
    await session.execute(
        sa_update(table)
        .where(table.c.id == user.id)
        .values(login_attempts=0, locked_until=None)
    )
    await session.flush()
    return user
