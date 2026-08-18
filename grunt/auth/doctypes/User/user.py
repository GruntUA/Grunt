"""User DocType controller — password hashing, authentication, and user CRUD.

All business logic related to the User document lives here.
The auth layer (JWT tokens, refresh tokens) remains in ``grunt.core.auth.service``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import anyio.to_thread
import bcrypt
import structlog

import grunt
from grunt.document.base import Document
from grunt.document.schema import Schema

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
    first_name: str
    last_name: str
    middle_name: str | None
    full_name: str
    avatar: str | None
    phone: str | None
    birth_date: str | None
    gender: str | None
    timezone: str | None
    bio: str | None
    is_active: bool
    is_superadmin: bool
    password: str | None
    hashed_password: str | None
    theme: str
    language: str | None
    login_attempts: int
    locked_until: datetime | None
    last_login: datetime | None
    mfa_enabled: bool
    mfa_secret: str | None

    async def validate(self) -> None:
        if not self.email:
            raise ValueError("Email є обов'язковим")
        if not self.first_name:
            raise ValueError("Ім'я є обов'язковим")
        if not self.last_name:
            raise ValueError("Прізвище є обов'язковим")

    async def before_save(self) -> None:
        """Construct full_name from components."""
        parts = [self.last_name, self.first_name, self.middle_name]
        self.full_name = " ".join([p.strip() for p in parts if p and p.strip()])

    async def before_insert(self) -> None:
        # If a plain-text password was passed through the generic API, hash it.
        raw = self.data.get("password")
        if raw:
            self.hashed_password = await hash_password(str(raw))
            self.data.pop("password", None)

    async def set_password(self, plain: str) -> None:
        """Hash and store a new password on this document."""
        self.hashed_password = await hash_password(plain)

    async def check_password(self, plain: str) -> bool:
        """Return True if plain matches the stored hashed password."""
        return await verify_password(plain, self.hashed_password or "")

    async def setup_mfa(self) -> dict:
        """Whitelisted method: Start MFA setup for the user."""
        from grunt.auth.mfa import begin_mfa_setup

        return await begin_mfa_setup(self)

    async def confirm_mfa(self, code: str) -> list[str]:
        """Whitelisted method: Confirm MFA setup with TOTP code."""
        from grunt.auth.mfa import confirm_mfa_setup

        return await confirm_mfa_setup(self, code)

    async def disable_mfa(self) -> None:
        """Whitelisted method: Disable MFA for the user."""
        from grunt.auth.mfa import disable_mfa

        await disable_mfa(self)


class UserPublic(Schema):
    """Fields safe to return from whoami/register/list_users_api."""

    fields = ("name", "email", "full_name", "roles", "is_superadmin")


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
    },
)


# ── Password helpers ──────────────────────────────────────────────────────


def _hash_password_sync(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_password_sync(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except AttributeError, ValueError:
        return False


async def hash_password(plain: str) -> str:
    """Hash a password off the event loop.

    bcrypt is deliberately slow (~100ms+); running it inline would block every
    other request served by the same worker for that whole time.
    """
    return await anyio.to_thread.run_sync(_hash_password_sync, plain)


async def verify_password(plain: str, hashed: str | None) -> bool:
    """Verify a password off the event loop (see :func:`hash_password`)."""
    if not hashed:
        return False
    return await anyio.to_thread.run_sync(_verify_password_sync, plain, hashed)


# ── User CRUD ─────────────────────────────────────────────────────────────


async def get_user_by_email(email: str) -> User | None:
    """Look up a user by email. Runs as SYSTEM_USER — needed pre-login, when
    no real user is in context yet."""
    from grunt.auth.doctypes.UserRole.user_role import get_user_roles
    from grunt.context import require_session

    session = require_session()
    async with grunt.system_context(session):
        user = await User.objects.filter(email=email).first()
        if user is None:
            return None
        user.data["roles"] = await get_user_roles(user.name)
        return user


async def get_user_by_id(user_id: str) -> User | None:
    """Look up a user by id. Runs as SYSTEM_USER — see :func:`get_user_by_email`."""
    from grunt.auth.doctypes.UserRole.user_role import get_user_roles
    from grunt.context import require_session

    session = require_session()
    async with grunt.system_context(session):
        user = await User.objects.filter(name=user_id).first()
        if user is None:
            return None
        user.data["roles"] = await get_user_roles(user.name)
        return user


async def list_users() -> list[User]:
    """List all users. Runs as SYSTEM_USER — callers (CLI, admin API) gate access
    themselves before calling this."""
    from grunt.auth.doctypes.UserRole.user_role import get_user_roles
    from grunt.context import require_session
    from grunt.site.manager import site_manager

    session = require_session()
    engine = site_manager.get_engine(site_manager.get_active_site())
    async with grunt.system_context(session, engine):
        users = await User.objects.limit(10_000).all()
        for user in users:
            user.data["roles"] = await get_user_roles(user.name)
        return users


async def create_user(
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    middle_name: str | None,
) -> User:
    """Create a new user. The first user automatically becomes superadmin."""
    from grunt.context import require_session
    from grunt.site.manager import site_manager

    session = require_session()
    engine = site_manager.get_engine(site_manager.get_active_site())
    async with grunt.system_context(session, engine):
        is_superadmin = await User.objects.count() == 0
        await User.objects.create(
            email=email,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            password=password,
            is_superadmin=is_superadmin,
            is_active=True,
        )
        logger.info("user.created", email=email, superadmin=is_superadmin)

    user = await get_user_by_email(email)
    assert user is not None
    return user


async def authenticate(email: str, password: str) -> User | None:
    """Return user if credentials are valid, else None.

    Tracks failed attempts and locks the account after _MAX_ATTEMPTS failures.
    Raises ``ValueError("locked")`` when the account is temporarily locked.
    """
    from grunt.context import require_session

    user = await get_user_by_email(email)
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

    async with grunt.system_context(require_session()):
        if not user.hashed_password or not await verify_password(password, user.hashed_password):
            new_attempts = (user.login_attempts or 0) + 1
            updates: dict = {"login_attempts": new_attempts}
            if new_attempts >= _MAX_ATTEMPTS:
                updates["locked_until"] = now + timedelta(minutes=_LOCKOUT_MINUTES)
                updates["login_attempts"] = 0
            await grunt.db.set_value("User", user.name, updates)
            return None

        await grunt.db.set_value("User", user.name, {"login_attempts": 0, "locked_until": None})

    return user


@grunt.whitelist(allow_guest=True)
async def register(
    email: str,
    password: str,
    first_name: str | None = None,
    last_name: str | None = None,
    middle_name: str | None = None,
) -> dict[str, Any]:
    """Register a new user."""
    existing = await get_user_by_email(email)
    if existing is not None:
        grunt.throw(f"User with email '{email}' already exists", "CONFLICT")

    user = await create_user(email, password, first_name or "", last_name or "", middle_name)
    return UserPublic.dump(user)


@grunt.whitelist()
async def whoami() -> dict[str, Any]:
    """Return the currently authenticated user."""
    user = await grunt.get_current_user()
    return {**UserPublic.dump(user), "mfa_enabled": bool(user.mfa_enabled)}


@grunt.whitelist(roles=["superadmin"])
async def list_users_api() -> list[dict[str, Any]]:
    """List all users. Superadmin only (enforced by the whitelist gate)."""
    return UserPublic.dump_many(await list_users())


@grunt.whitelist(roles=["superadmin"])
async def add_role(user_id: str, role_name: str) -> dict[str, Any]:
    """Assign a role to a user. Superadmin only (enforced by the whitelist gate)."""
    await grunt.get_doc(User, user_id)  # raises 404 if the user doesn't exist

    existing_role = await grunt.get_list("Role", filters={"role_name": role_name}, limit=1)
    if not existing_role:
        await grunt.new_doc("Role", {"role_name": role_name})

    existing_assignment = await grunt.get_list(
        "UserRole",
        filters={"user_id": user_id, "role_name": role_name},
        limit=1,
    )
    if existing_assignment:
        return {"user_id": user_id, "role": role_name, "message": "Роль вже призначено"}

    await grunt.new_doc("UserRole", {"user_id": user_id, "role_name": role_name})
    return {"user_id": user_id, "role": role_name}


@grunt.whitelist(roles=["superadmin"])
async def remove_role(user_id: str, role_name: str) -> bool:
    """Remove a role from a user. Superadmin only (enforced by the whitelist gate)."""
    rows = await grunt.get_list(
        "UserRole",
        filters={"user_id": user_id, "role_name": role_name},
        fields=["name"],
        limit=1,
    )
    if not rows:
        grunt.throw("Роль не знайдено у користувача", "NOT_FOUND")

    await grunt.delete_doc("UserRole", rows[0]["name"])
    return True


@grunt.whitelist()
async def setup_mfa() -> dict[str, Any]:
    """Whitelisted method: Start MFA setup for the current user."""
    current = await grunt.get_current_user()
    user = await get_user_by_id(current.id)
    if not user:
        grunt.throw("User not found")
    return await user.setup_mfa()


@grunt.whitelist()
async def confirm_mfa(code: str) -> dict[str, Any]:
    """Whitelisted method: Confirm MFA setup for the current user."""
    current = await grunt.get_current_user()
    user = await get_user_by_id(current.id)
    if not user:
        grunt.throw("User not found")
    backup_codes = await user.confirm_mfa(code)
    return {"backup_codes": backup_codes}


@grunt.whitelist()
async def disable_mfa() -> bool:
    """Whitelisted method: Disable MFA for the current user."""
    current = await grunt.get_current_user()
    user = await get_user_by_id(current.id)
    if not user:
        grunt.throw("User not found")
    await user.disable_mfa()
    return True
