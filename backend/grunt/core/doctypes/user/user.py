"""User DocType controller — password hashing, authentication, and user CRUD.

All business logic related to the User document lives here.
The auth layer (JWT tokens, refresh tokens) remains in ``grunt.core.auth.service``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import bcrypt
import structlog
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from grunt.core.document.base import Document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger()

_MAX_ATTEMPTS = 10
_LOCKOUT_MINUTES = 30


class GruntUser(BaseModel):
    """Runtime user object populated from the ``User`` DocType.

    Not a SQLAlchemy ORM model — use ``grunt.core.doctypes.User.User``
    helpers to load/create users.
    """

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    full_name: str = ""
    hashed_password: str = ""
    is_active: bool = True
    is_superadmin: bool = False
    theme: str = "system"
    login_attempts: int = 0
    locked_until: datetime | None = None
    mfa_enabled: bool = False
    mfa_secret: str = ""
    created_at: datetime | None = None
    modified_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)


# Convenience system-user singleton for internal tasks.
SYSTEM_USER = GruntUser(
    email="system@grunt.local",
    full_name="System",
    is_superadmin=True,
)


# ── Password helpers ──────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Internal helpers ──────────────────────────────────────────────────────


def _user_table():
    """Return the SQLAlchemy Core Table for the User DocType (grunt_core_user).

    Used only in bootstrap/low-level paths (create_user, password reset).
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


def _row_to_user(row: dict, roles: list[str]) -> GruntUser:
    return GruntUser(
        id=row["id"],
        email=row.get("email") or "",
        full_name=row.get("full_name") or "",
        hashed_password=row.get("hashed_password") or "",
        is_active=bool(row["is_active"]) if row.get("is_active") is not None else True,
        is_superadmin=bool(row["is_superadmin"]) if row.get("is_superadmin") is not None else False,
        theme=row.get("theme") or "system",
        login_attempts=int(row["login_attempts"]) if row.get("login_attempts") is not None else 0,
        locked_until=row.get("locked_until"),
        mfa_enabled=bool(row["mfa_enabled"]) if row.get("mfa_enabled") is not None else False,
        mfa_secret=row.get("mfa_secret") or "",
        created_at=row.get("created_at"),
        modified_at=row.get("modified_at"),
        roles=roles,
    )


# ── User CRUD ─────────────────────────────────────────────────────────────


# Fields needed for session auth — excludes hashed_password, mfa_secret, mfa_backup_codes
_SESSION_FIELDS = [
    "id",
    "email",
    "full_name",
    "is_active",
    "is_superadmin",
    "theme",
    "mfa_enabled",
    "login_attempts",
    "locked_until",
]


async def get_user_by_email(
    email: str,
    session: AsyncSession,
    fields: list[str] | None = None,
) -> GruntUser | None:
    from grunt.app import grunt  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        from grunt.core.doctypes.user_role.user_role import get_user_roles  # noqa: PLC0415

        rows = await grunt.db.get_all("User", filters={"email": email}, fields=fields, limit=1)
        if not rows:
            return None
        row = rows[0]
        roles = await get_user_roles(row["id"], session)
        return _row_to_user(row, roles)
    finally:
        grunt.reset_context(_tokens)


async def get_user_by_id(user_id: str, session: AsyncSession) -> GruntUser | None:
    from grunt.app import grunt  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        from grunt.core.doctypes.user_role.user_role import get_user_roles  # noqa: PLC0415

        rows = await grunt.db.get_all("User", filters={"id": user_id}, limit=1)
        if not rows:
            return None
        row = rows[0]
        roles = await get_user_roles(row["id"], session)
        return _row_to_user(row, roles)
    finally:
        grunt.reset_context(_tokens)


async def list_users(session: AsyncSession) -> list[GruntUser]:
    from grunt.app import grunt  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        from grunt.core.doctypes.user_role.user_role import get_user_roles  # noqa: PLC0415

        rows = await grunt.db.get_all("User", limit=10_000)
        users = []
        for row in rows:
            roles = await get_user_roles(row["id"], session)
            users.append(_row_to_user(row, roles))
        return users
    finally:
        grunt.reset_context(_tokens)


async def create_user(
    email: str,
    password: str,
    full_name: str,
    session: AsyncSession,
) -> GruntUser:
    """Create a new user. The first user automatically becomes superadmin.

    Uses a raw insert to bypass the permission layer during bootstrap.
    """
    table = _user_table()

    count_result = await session.execute(select(func.count()).select_from(table))
    user_count = count_result.scalar() or 0

    user_id = str(uuid.uuid4())
    now = datetime.now(UTC)
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


async def authenticate(email: str, password: str, session: AsyncSession) -> GruntUser | None:
    """Return user if credentials are valid, else None.

    Tracks failed attempts and locks the account after _MAX_ATTEMPTS failures.
    Raises ``ValueError("locked")`` when the account is temporarily locked.
    """
    from grunt.app import grunt  # noqa: PLC0415

    user = await get_user_by_email(email, session)
    if user is None:
        return None

    now = datetime.now(UTC)

    if user.locked_until:
        if user.locked_until.tzinfo is not None and user.locked_until.utcoffset() is not None:
            locked_until_utc = user.locked_until.astimezone(UTC)
        else:
            locked_until_utc = user.locked_until.replace(tzinfo=UTC)
        if locked_until_utc > now:
            raise ValueError("locked")

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        if not verify_password(password, user.hashed_password):
            new_attempts = (user.login_attempts or 0) + 1
            updates: dict = {"login_attempts": new_attempts}
            if new_attempts >= _MAX_ATTEMPTS:
                updates["locked_until"] = now + timedelta(minutes=_LOCKOUT_MINUTES)
                updates["login_attempts"] = 0
            await grunt.db.set_value("User", user.id, updates)
            return None

        await grunt.db.set_value("User", user.id, {"login_attempts": 0, "locked_until": None})
    finally:
        grunt.reset_context(_tokens)

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
