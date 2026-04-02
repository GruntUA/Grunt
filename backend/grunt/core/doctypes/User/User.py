"""User DocType controller — password hashing, authentication, and user CRUD.

All business logic related to the User document lives here.
The auth layer (JWT tokens, refresh tokens) remains in ``grunt.core.auth.service``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import structlog
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.document.base import Document

logger = structlog.get_logger()

_MAX_ATTEMPTS = 10
_LOCKOUT_MINUTES = 30


# ── Password helpers ──────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Table / row helpers ───────────────────────────────────────────────────


def _user_table() -> Table:
    """Return the SQLAlchemy Core Table for the User DocType (grunt_core_user)."""
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    dt = doctype_registry._doctypes.get("User")
    if dt is None:
        raise RuntimeError(
            "DocType 'User' not found in registry. "
            "Ensure load_core_doctypes() ran before auth operations."
        )
    return compile_doctype_to_table(dt)


async def _load_user_roles(user_id: str, session: AsyncSession):
    from grunt.core.auth.models import GruntUserRole  # noqa: PLC0415

    result = await session.execute(
        select(GruntUserRole).where(GruntUserRole.user_id == user_id)
    )
    return list(result.scalars().all())


def _row_to_user(row: dict, user_roles: list):
    from grunt.core.auth.models import GruntUser  # noqa: PLC0415

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


# ── User CRUD ─────────────────────────────────────────────────────────────


async def get_user_by_email(email: str, session: AsyncSession):
    table = _user_table()
    result = await session.execute(select(table).where(table.c.email == email))
    row = result.mappings().one_or_none()
    if row is None:
        return None
    user_roles = await _load_user_roles(row["id"], session)
    return _row_to_user(dict(row), user_roles)


async def get_user_by_id(user_id: str, session: AsyncSession):
    table = _user_table()
    result = await session.execute(select(table).where(table.c.id == user_id))
    row = result.mappings().one_or_none()
    if row is None:
        return None
    user_roles = await _load_user_roles(row["id"], session)
    return _row_to_user(dict(row), user_roles)


async def list_users(session: AsyncSession):
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
):
    """Create a new user. The first user automatically becomes superadmin."""
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
    logger.info("user.created", email=email, superadmin=is_superadmin)

    user = await get_user_by_email(email, session)
    assert user is not None
    return user


async def authenticate(email: str, password: str, session: AsyncSession):
    """Return user if credentials are valid, else None.

    Tracks failed attempts and locks the account after _MAX_ATTEMPTS failures.
    Raises ``ValueError("locked")`` when the account is temporarily locked.
    """
    from sqlalchemy import update as sa_update  # noqa: PLC0415

    user = await get_user_by_email(email, session)
    if user is None:
        return None

    now = datetime.now(timezone.utc)

    if user.locked_until:
        if user.locked_until.tzinfo is not None and user.locked_until.utcoffset() is not None:
            locked_until_utc = user.locked_until.astimezone(timezone.utc)
        else:
            locked_until_utc = user.locked_until.replace(tzinfo=timezone.utc)
        if locked_until_utc > now:
            raise ValueError("locked")

    if not verify_password(password, user.hashed_password):
        new_attempts = (user.login_attempts or 0) + 1
        values: dict = {"login_attempts": new_attempts}
        if new_attempts >= _MAX_ATTEMPTS:
            values["locked_until"] = now + timedelta(minutes=_LOCKOUT_MINUTES)
            values["login_attempts"] = 0
        table = _user_table()
        await session.execute(
            sa_update(table).where(table.c.id == user.id).values(**values)
        )
        await session.flush()
        return None

    table = _user_table()
    await session.execute(
        sa_update(table)
        .where(table.c.id == user.id)
        .values(login_attempts=0, locked_until=None)
    )
    await session.flush()
    return user


# ── Document Controller ───────────────────────────────────────────────────


class User(Document):
    """DocType controller for User.

    Handles lifecycle hooks when User documents are created or updated
    through the generic document API (form, import, etc.).
    """

    # Field annotations for IDE support — values live in self.data at runtime.
    email: str
    full_name: str
    is_active: bool
    is_superadmin: bool
    hashed_password: str
    theme: str
    login_attempts: int
    locked_until: datetime | None
    mfa_enabled: bool
    mfa_secret: str

    async def validate(self) -> None:
        if not self.email:
            raise ValueError("Email є обов'язковим")
        if not self.full_name:
            raise ValueError("Повне ім'я є обов'язковим")

    async def before_insert(self) -> None:
        # If a plain-text password was passed through the generic API, hash it.
        raw = self.data.get("password")
        if raw:
            self.hashed_password = hash_password(str(raw))
            self.data.pop("password", None)

    def set_password(self, plain: str) -> None:
        """Hash and store a new password on this document."""
        self.hashed_password = hash_password(plain)

    def check_password(self, plain: str) -> bool:
        """Return True if plain matches the stored hashed password."""
        return verify_password(plain, self.hashed_password or "")
