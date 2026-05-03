"""User DocType controller — password hashing, authentication, and user CRUD.

All business logic related to the User document lives here.
The auth layer (JWT tokens, refresh tokens) remains in ``grunt.core.auth.service``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import bcrypt
import structlog

import grunt
from grunt.document.base import Document

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
            self.hashed_password = hash_password(str(raw))
            self.data.pop("password", None)

    def set_password(self, plain: str) -> None:
        """Hash and store a new password on this document."""
        self.hashed_password = hash_password(plain)

    def check_password(self, plain: str) -> bool:
        """Return True if plain matches the stored hashed password."""
        return verify_password(plain, self.hashed_password or "")

    async def setup_mfa(self) -> dict:
        """Whitelisted method: Start MFA setup for the user."""
        from grunt.auth.mfa import begin_mfa_setup  # noqa: PLC0415

        return await begin_mfa_setup(self)

    async def confirm_mfa(self, code: str) -> list[str]:
        """Whitelisted method: Confirm MFA setup with TOTP code."""
        from grunt.auth.mfa import confirm_mfa_setup  # noqa: PLC0415

        return await confirm_mfa_setup(self, code)

    async def disable_mfa(self) -> None:
        """Whitelisted method: Disable MFA for the user."""
        from grunt.auth.mfa import disable_mfa  # noqa: PLC0415

        await disable_mfa(self)


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


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except (AttributeError, ValueError):
        return False


# ── User CRUD ─────────────────────────────────────────────────────────────


async def get_user_by_email(
    email: str,
    session: AsyncSession,
) -> User | None:
    from grunt.app import grunt  # noqa: PLC0415

    async with grunt.system_context(session):
        from grunt.auth.doctypes.UserRole.UserRole import get_user_roles  # noqa: PLC0415

        rows = await grunt.db.get_all("User", filters={"email": email}, limit=1)
        if not rows:
            return None
        row = rows[0]
        roles = await get_user_roles(row["id"], session)
        return User(doctype="User", data={**row, "roles": roles})


async def get_user_by_id(user_id: str, session: AsyncSession) -> User | None:
    from grunt.app import grunt  # noqa: PLC0415

    async with grunt.system_context(session):
        from grunt.auth.doctypes.UserRole.UserRole import get_user_roles  # noqa: PLC0415

        rows = await grunt.db.get_all("User", filters={"id": user_id}, limit=1)
        if not rows:
            return None
        row = rows[0]
        roles = await get_user_roles(row["id"], session)
        return User(doctype="User", data={**row, "roles": roles})


async def list_users(session: AsyncSession) -> list[User]:
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.site.manager import site_manager  # noqa: PLC0415

    _engine = site_manager.get_engine(site_manager.get_active_site())
    async with grunt.system_context(session, _engine):
        from grunt.auth.doctypes.UserRole.UserRole import get_user_roles  # noqa: PLC0415

        rows = await grunt.db.get_all("User", limit=10_000)
        users = []
        for row in rows:
            roles = await get_user_roles(row["id"], session)
            users.append(User(doctype="User", data={**row, "roles": roles}))
        return users


async def create_user(
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    middle_name: str | None,
    session: AsyncSession,
) -> User:
    """Create a new user. The first user automatically becomes superadmin."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.site.manager import site_manager  # noqa: PLC0415

    _engine = site_manager.get_engine(site_manager.get_active_site())
    async with grunt.system_context(session, _engine):
        user_count = await grunt.db.count("User")
        is_superadmin = user_count == 0

        await grunt.new_doc(
            "User",
            {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "password": password,
                "is_superadmin": is_superadmin,
                "is_active": True,
            },
        )

        logger.info("user.created", email=email, superadmin=is_superadmin)

        user = await get_user_by_email(email, session)
        assert user is not None
        return user


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

    async with grunt.system_context(session):
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            new_attempts = (user.login_attempts or 0) + 1
            updates: dict = {"login_attempts": new_attempts}
            if new_attempts >= _MAX_ATTEMPTS:
                updates["locked_until"] = now + timedelta(minutes=_LOCKOUT_MINUTES)
                updates["login_attempts"] = 0
            await grunt.db.set_value("User", user.id, updates)
            return None

        await grunt.db.set_value("User", user.id, {"login_attempts": 0, "locked_until": None})

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
    from grunt.app import grunt as grunt_app  # noqa: PLC0415

    session = grunt_app._require_session()

    existing = await get_user_by_email(email, session)
    if existing is not None:
        grunt_app.throw(f"User with email '{email}' already exists", "CONFLICT")

    user = await create_user(
        email,
        password,
        first_name or "",
        last_name or "",
        middle_name,
        session,
    )
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": user.roles,
        "is_superadmin": user.is_superadmin,
    }


@grunt.whitelist()
async def whoami() -> dict[str, Any]:
    """Return the currently authenticated user."""
    from grunt.app import grunt as grunt_app  # noqa: PLC0415

    user = grunt_app._require_user()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": user.roles,
        "is_superadmin": user.is_superadmin,
        "mfa_enabled": bool(user.mfa_enabled),
    }


@grunt.whitelist()
async def list_users_api() -> list[dict[str, Any]]:
    """List all users. Superadmin only."""
    from grunt.app import grunt as grunt_app  # noqa: PLC0415

    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt_app.throw("Unauthorized", "PERMISSION_DENIED")

    users = await list_users(grunt_app._require_session())
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "roles": u.roles,
            "is_superadmin": u.is_superadmin,
        }
        for u in users
    ]


@grunt.whitelist()
async def add_role(user_id: str, role_name: str) -> dict[str, Any]:
    """Assign a role to a user. Superadmin only."""
    from grunt.app import grunt as grunt_app  # noqa: PLC0415

    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt_app.throw("Unauthorized", "PERMISSION_DENIED")

    target_user = await get_user_by_id(user_id, grunt_app._require_session())
    if not target_user:
        grunt_app.throw("Користувача не знайдено", "NOT_FOUND")

    # Check if role exists, create if not
    existing_role = await grunt_app.get_list("Role", filters={"role_name": role_name}, limit=1)
    if not existing_role:
        await grunt_app.new_doc("Role", {"role_name": role_name})

    existing_assignment = await grunt_app.get_list(
        "UserRole",
        filters={"user_id": user_id, "role_name": role_name},
        limit=1,
    )
    if existing_assignment:
        return {"user_id": user_id, "role": role_name, "message": "Роль вже призначено"}

    await grunt_app.new_doc("UserRole", {"user_id": user_id, "role_name": role_name})
    return {"user_id": user_id, "role": role_name}


@grunt.whitelist()
async def remove_role(user_id: str, role_name: str) -> bool:
    """Remove a role from a user. Superadmin only."""
    from grunt.app import grunt as grunt_app  # noqa: PLC0415

    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt_app.throw("Unauthorized", "PERMISSION_DENIED")

    rows = await grunt_app.get_list(
        "UserRole",
        filters={"user_id": user_id, "role_name": role_name},
        fields=["id"],
        limit=1,
    )
    if not rows:
        grunt_app.throw("Роль не знайдено у користувача", "NOT_FOUND")

    await grunt_app.delete_doc("UserRole", rows[0]["id"])
    return True


@grunt.whitelist()
async def setup_mfa() -> dict[str, Any]:
    """Whitelisted method: Start MFA setup for the current user."""
    from grunt.app import grunt as grunt_app  # noqa: PLC0415

    current = grunt_app._require_user()
    session = grunt_app._require_session()
    user = await get_user_by_id(current.id, session)
    if not user:
        grunt_app.throw("User not found")
    return await user.setup_mfa()


@grunt.whitelist()
async def confirm_mfa(code: str) -> dict[str, Any]:
    """Whitelisted method: Confirm MFA setup for the current user."""
    from grunt.app import grunt as grunt_app  # noqa: PLC0415

    current = grunt_app._require_user()
    session = grunt_app._require_session()
    user = await get_user_by_id(current.id, session)
    if not user:
        grunt_app.throw("User not found")
    backup_codes = await user.confirm_mfa(code)
    return {"backup_codes": backup_codes}


@grunt.whitelist()
async def disable_mfa() -> bool:
    """Whitelisted method: Disable MFA for the current user."""
    from grunt.app import grunt as grunt_app  # noqa: PLC0415

    current = grunt_app._require_user()
    session = grunt_app._require_session()
    user = await get_user_by_id(current.id, session)
    if not user:
        grunt_app.throw("User not found")
    await user.disable_mfa()
    return True
