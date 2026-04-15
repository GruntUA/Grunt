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
from grunt.core.document.base import Document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger()

_MAX_ATTEMPTS = 10
_LOCKOUT_MINUTES = 30

# ── Document Controller ───────────────────────────────────────────────────


class User(Document):
    """DocType controller for User.

    Handles lifecycle hooks when User documents are created or updated
    through the generic document API (form, import, etc.).
    """

    # Field annotations for IDE support — values live in self.data at runtime.
    email: str
    full_name: str
    avatar: str | None
    phone: str | None
    bio: str | None
    is_active: bool
    is_superadmin: bool
    password: str | None
    hashed_password: str | None
    theme: str
    language: str | None
    login_attempts: int
    locked_until: datetime | None
    mfa_enabled: bool
    mfa_secret: str | None

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


# Convenience system-user singleton for internal tasks.
SYSTEM_USER = User(
    doctype="User",
    data={
        "email": "system@grunt.local",
        "full_name": "System",
        "is_superadmin": True,
        "is_active": True,
        "theme": "system",
        "language": "uk",
    }
)


# ── Password helpers ──────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _row_to_user(row: dict, roles: list[str]) -> User:
    data = dict(row)
    # Ensure defaults for boolean fields logic
    if data.get("is_active") is None:
        data["is_active"] = True
    else:
        data["is_active"] = bool(data["is_active"])
        
    if data.get("is_superadmin") is None:
        data["is_superadmin"] = False
    else:
        data["is_superadmin"] = bool(data["is_superadmin"])
        
    data["theme"] = data.get("theme") or "system"
    data["language"] = data.get("language") or "uk"
    data["login_attempts"] = int(data.get("login_attempts") or 0)
    data["mfa_enabled"] = bool(data.get("mfa_enabled"))
    data["roles"] = roles
    
    return User(doctype="User", data=data)


# ── User CRUD ─────────────────────────────────────────────────────────────


async def get_user_by_email(
    email: str,
    session: AsyncSession,
) -> User | None:
    from grunt.app import grunt  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        from grunt.core.doctypes.user_role.user_role import get_user_roles  # noqa: PLC0415

        rows = await grunt.db.get_all("User", filters={"email": email}, limit=1)
        if not rows:
            return None
        row = rows[0]
        roles = await get_user_roles(row["id"], session)
        return _row_to_user(row, roles)
    finally:
        grunt.reset_context(_tokens)


async def get_user_by_id(user_id: str, session: AsyncSession) -> User | None:
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


async def list_users(session: AsyncSession) -> list[User]:
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.site.manager import site_manager  # noqa: PLC0415

    _engine = site_manager.get_engine(site_manager.get_active_site())
    _tokens = grunt.set_context(session, _engine, SYSTEM_USER)
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
) -> User:
    """Create a new user. The first user automatically becomes superadmin."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.site.manager import site_manager  # noqa: PLC0415

    _engine = site_manager.get_engine(site_manager.get_active_site())
    _tokens = grunt.set_context(session, _engine, SYSTEM_USER)
    
    try:
        user_count = await grunt.db.count("User")
        is_superadmin = user_count == 0

        doc = await grunt.new_doc("User", {
            "email": email,
            "full_name": full_name,
            "password": password,
            "is_superadmin": is_superadmin,
            "is_active": True
        })
        await doc.insert()
        
        logger.info("user.created", email=email, superadmin=is_superadmin)

        user = await get_user_by_email(email, session)
        assert user is not None
        return user
    finally:
        grunt.reset_context(_tokens)


async def authenticate(email: str, password: str, session: AsyncSession) -> User | None:
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


