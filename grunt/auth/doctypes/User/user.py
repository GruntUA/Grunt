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
            if not await _is_internal_context():
                # Interactive create (admin form / import) — hold it to policy.
                # The register_* endpoints already checked before reaching here.
                from grunt.auth.password_policy import enforce_password_policy

                await enforce_password_policy(str(raw))
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
    except (AttributeError, ValueError):
        return False


async def _is_internal_context() -> bool:
    """True when the active context is the internal SYSTEM_USER (bootstrap,
    fixtures, registration flows) or has no user at all — those paths must not
    be blocked by the interactive password policy."""
    try:
        current = await grunt.get_current_user()
    except Exception:
        return True
    return not current or current.email == SYSTEM_USER.email


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


async def _get_user_by(**filter_kwargs: str) -> User | None:
    """Look up a user by a single field (email or name). Runs as SYSTEM_USER —
    needed pre-login, when no real user is in context yet."""
    from grunt.auth.doctypes.UserRole.user_role import get_user_roles
    from grunt.context import require_session

    session = require_session()
    async with grunt.system_context(session):
        user = await User.objects.filter(**filter_kwargs).first()
        if user is None:
            return None
        user.data["roles"] = await get_user_roles(user.name)
        return user


async def get_user_by_email(email: str) -> User | None:
    """Look up a user by email. See :func:`_get_user_by`."""
    return await _get_user_by(email=email)


async def get_user_by_id(user_id: str) -> User | None:
    """Look up a user by id. See :func:`_get_user_by`."""
    return await _get_user_by(name=user_id)


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

    Tracks failed attempts and locks the account after ``max_login_attempts``
    (``SystemSettings``) failures for ``account_lockout_duration`` minutes.
    Raises ``ValueError("locked")`` when the account is temporarily locked.
    """
    from grunt.context import require_session
    from grunt.site.settings import get_setting

    user = await get_user_by_email(email)
    if user is None:
        return None

    max_attempts = int(await get_setting("max_login_attempts", _MAX_ATTEMPTS) or _MAX_ATTEMPTS)
    lockout_minutes = int(
        await get_setting("account_lockout_duration", _LOCKOUT_MINUTES) or _LOCKOUT_MINUTES
    )

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
            if new_attempts >= max_attempts:
                updates["locked_until"] = now + timedelta(minutes=lockout_minutes)
                updates["login_attempts"] = 0
            await grunt.db.set_value("User", user.name, updates)
            return None

        await grunt.db.set_value("User", user.name, {"login_attempts": 0, "locked_until": None})

    return user


def _auth_user_dump(user: User) -> dict[str, Any]:
    """Full user payload expected by auth UI responses."""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": user.roles,
        "is_superadmin": bool(user.is_superadmin),
        "theme": user.theme,
        "avatar": user.avatar,
        "mfa_enabled": bool(user.mfa_enabled),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


async def _track_login_session(
    user_id: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Best-effort session tracking for successful logins."""
    try:
        from grunt.auth.doctypes.UserSession.user_session import create_session

        await create_session(user_id, ip_address, user_agent)
    except Exception:
        logger.exception("suppressed_error")


async def _guard_registration() -> None:
    """Block self-service registration unless ``allow_user_registration`` is on.

    The very first user is always allowed — that path is the setup wizard /
    ``grunt site create`` bootstrap, not public sign-up.
    """
    from grunt.site.settings import get_setting

    if await grunt.db.count("User") == 0:
        return
    if not await get_setting("allow_user_registration", False):
        grunt.throw("Реєстрація нових користувачів вимкнена", "FORBIDDEN")


async def _assign_default_role(user_id: str | None) -> None:
    """Give a freshly registered user the configured ``default_role`` (if any)."""
    from grunt.site.settings import get_setting

    role = await get_setting("default_role")
    if not role or not user_id:
        return
    existing = await grunt.get_list(
        "UserRole",
        filters={"user_id": user_id, "role_name": role},
        fields=["name"],
        limit=1,
    )
    if not existing:
        await grunt.new_doc("UserRole", {"user_id": user_id, "role_name": role})


@grunt.whitelist(allow_guest=True)
async def register(
    email: str,
    password: str,
    first_name: str | None = None,
    last_name: str | None = None,
    middle_name: str | None = None,
) -> dict[str, Any]:
    """Register a new user."""
    from grunt.auth.password_policy import enforce_password_policy

    await _guard_registration()
    await enforce_password_policy(password)

    existing = await get_user_by_email(email)
    if existing is not None:
        grunt.throw(f"User with email '{email}' already exists", "CONFLICT")

    user = await create_user(email, password, first_name or "", last_name or "", middle_name)
    await _assign_default_role(user.id)
    return UserPublic.dump(user)


@grunt.whitelist(allow_guest=True)
async def register_full_name_api(email: str, password: str, full_name: str) -> dict[str, Any]:
    """Register a new user using a single full_name string."""
    from grunt.auth.password_policy import enforce_password_policy

    await _guard_registration()
    await enforce_password_policy(password)

    name_parts = full_name.split(maxsplit=1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    user = await create_user(email, password, first_name, last_name, None)
    await _assign_default_role(user.id)
    return _auth_user_dump(user)


@grunt.whitelist(allow_guest=True)
async def login_api(
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Authenticate a user and issue auth tokens or MFA challenge token."""
    from grunt.auth.service import (
        create_access_token,
        create_mfa_token,
        create_refresh_token,
        session_ttl_minutes,
    )

    try:
        user = await authenticate(email, password)
    except ValueError as exc:
        if str(exc) == "locked":
            grunt.throw("Account temporarily locked. Try again later.", "TOO_MANY_REQUESTS")
        raise

    if user is None:
        grunt.throw("Incorrect email or password", "UNAUTHORIZED")

    if user.mfa_enabled:
        return {
            "access_token": None,
            "refresh_token": None,
            "mfa_token": create_mfa_token(user),
            "token_type": "bearer",
            "user": _auth_user_dump(user),
            "mfa_required": True,
        }

    assert user.id is not None
    ttl = await session_ttl_minutes()
    access_token = create_access_token(user, ttl)
    refresh_token = await create_refresh_token(user.id, ttl)
    await _track_login_session(user.id, ip_address, user_agent)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "mfa_token": None,
        "token_type": "bearer",
        "user": _auth_user_dump(user),
        "mfa_required": False,
    }


@grunt.whitelist(allow_guest=True)
async def mfa_login_api(
    mfa_token: str,
    code: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Verify MFA challenge token+code and issue full auth tokens."""
    from grunt.auth.mfa import check_mfa_code
    from grunt.auth.service import (
        create_access_token,
        create_refresh_token,
        session_ttl_minutes,
        verify_mfa_token,
    )

    payload = verify_mfa_token(mfa_token)
    if not payload:
        grunt.throw("Невалідний або прострочений MFA токен", "UNAUTHORIZED")

    user = await get_user_by_id(payload["uid"])
    if not user or not user.is_active:
        grunt.throw("Користувача не знайдено", "UNAUTHORIZED")

    try:
        await check_mfa_code(user, code)
    except Exception as exc:
        logger.error("auth.mfa_verify_error", error=str(exc))
        raise

    assert user.id is not None
    ttl = await session_ttl_minutes()
    access_token = create_access_token(user, ttl)
    refresh_token = await create_refresh_token(user.id, ttl)
    await _track_login_session(user.id, ip_address, user_agent)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "mfa_token": None,
        "token_type": "bearer",
        "user": _auth_user_dump(user),
        "mfa_required": False,
    }


@grunt.whitelist()
async def whoami() -> dict[str, Any]:
    """Return the currently authenticated user."""
    user = await grunt.get_current_user()
    return {**UserPublic.dump(user), "mfa_enabled": bool(user.mfa_enabled)}


@grunt.whitelist()
async def me_api() -> dict[str, Any]:
    """Return current user with the full auth payload fields."""
    user = await grunt.get_current_user()
    return _auth_user_dump(user)


@grunt.whitelist()
async def update_me_api(theme: str | None = None) -> dict[str, Any]:
    """Update current user preferences and return updated profile."""
    user = await grunt.get_current_user()

    values: dict[str, Any] = {}
    if theme is not None:
        if theme not in ("light", "dark", "system"):
            grunt.throw("Invalid theme value", "VALIDATION_ERROR")
        values["theme"] = theme

    assert user.id is not None
    if values:
        await grunt.set_value("User", user.id, values)

    updated = await get_user_by_id(user.id)
    if updated is None:
        grunt.throw("User not found", "NOT_FOUND")
    return _auth_user_dump(updated)


@grunt.whitelist(allow_guest=True)
async def refresh_api(refresh_token: str) -> dict[str, Any]:
    """Exchange a valid refresh token for a new access+refresh pair."""
    from grunt.auth.service import (
        create_access_token,
        rotate_refresh_token,
        session_ttl_minutes,
    )

    result = await rotate_refresh_token(refresh_token)
    if result is None:
        grunt.throw("Invalid or expired refresh token", "UNAUTHORIZED")

    new_refresh_token, user = result
    return {
        "access_token": create_access_token(user, await session_ttl_minutes()),
        "refresh_token": new_refresh_token,
        "mfa_token": None,
        "token_type": "bearer",
        "user": _auth_user_dump(user),
        "mfa_required": False,
    }


@grunt.whitelist()
async def logout_api() -> bool:
    """Revoke current user's refresh tokens and terminate active sessions."""
    from grunt.auth.service import revoke_refresh_tokens_for_user

    user = await grunt.get_current_user()
    assert user.id is not None

    await revoke_refresh_tokens_for_user(user.id)
    try:
        from grunt.auth.doctypes.UserSession.user_session import terminate_all_user_sessions

        await terminate_all_user_sessions(user.id)
    except Exception:
        logger.exception("suppressed_error")

    return True


@grunt.whitelist(roles=["superadmin"])
async def list_users_api() -> list[dict[str, Any]]:
    """List all users. Superadmin only (enforced by the whitelist gate)."""
    return UserPublic.dump_many(await list_users())


@grunt.whitelist(roles=["superadmin"])
async def list_users_detailed_api() -> list[dict[str, Any]]:
    """List all users with fields needed by the admin REST endpoint."""
    users = await list_users()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "roles": u.roles,
            "is_superadmin": bool(u.is_superadmin),
            "theme": u.theme,
            "avatar": u.avatar,
            "mfa_enabled": bool(u.mfa_enabled),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@grunt.whitelist(roles=["superadmin"])
async def list_roles_api() -> list[dict[str, Any]]:
    """List all defined roles. Superadmin only."""
    roles = await grunt.get_list("Role", fields=["role_name", "description"], limit=1000)
    return [{"name": r["role_name"], "description": r.get("description")} for r in roles]


@grunt.whitelist(roles=["superadmin"])
async def create_role_api(role_name: str) -> dict[str, Any]:
    """Create a role if it doesn't exist. Superadmin only."""
    existing = await grunt.get_list("Role", filters={"role_name": role_name}, limit=1)
    if existing:
        grunt.throw(f"Роль '{role_name}' вже існує", "CONFLICT")

    doc = await grunt.new_doc("Role", {"role_name": role_name})
    return {"name": doc["role_name"]}


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


@grunt.whitelist(roles=["superadmin"])
async def set_user_password_api(user_id: str, new_password: str) -> bool:
    """Set a new password for a user. Superadmin only."""
    from grunt.auth.password_policy import enforce_password_policy

    user = await get_user_by_id(user_id)
    if not user or not user.id:
        grunt.throw("Користувача не знайдено", "NOT_FOUND")

    await enforce_password_policy(new_password)
    await grunt.set_value("User", user.id, "hashed_password", await hash_password(new_password))
    return True


@grunt.whitelist()
async def setup_mfa() -> dict[str, Any]:
    """Whitelisted method: Start MFA setup for the current user."""
    current = await grunt.get_current_user()
    assert current.id is not None
    user = await get_user_by_id(current.id)
    if not user:
        grunt.throw("User not found")
    return await user.setup_mfa()


@grunt.whitelist()
async def confirm_mfa(code: str) -> dict[str, Any]:
    """Whitelisted method: Confirm MFA setup for the current user."""
    current = await grunt.get_current_user()
    assert current.id is not None
    user = await get_user_by_id(current.id)
    if not user:
        grunt.throw("User not found")
    backup_codes = await user.confirm_mfa(code)
    return {"backup_codes": backup_codes}


@grunt.whitelist()
async def verify_mfa(code: str) -> bool:
    """Verify a TOTP or backup code for the current user."""
    from grunt.auth.mfa import check_mfa_code

    current = await grunt.get_current_user()
    assert current.id is not None
    user = await get_user_by_id(current.id)
    if not user:
        grunt.throw("User not found", "NOT_FOUND")

    await check_mfa_code(user, code)
    return True


@grunt.whitelist()
async def disable_mfa() -> bool:
    """Whitelisted method: Disable MFA for the current user."""
    current = await grunt.get_current_user()
    assert current.id is not None
    user = await get_user_by_id(current.id)
    if not user:
        grunt.throw("User not found")
    await user.disable_mfa()
    return True


@grunt.whitelist(allow_guest=True)
async def forgot_password_api(email: str) -> bool:
    """Queue a password reset email if the user exists (always returns success)."""
    import structlog

    from grunt.auth.service import create_password_reset_token
    from grunt.config import settings
    from grunt.context import require_session

    log = structlog.get_logger()
    user = await get_user_by_email(email)
    if user is None or not user.id:
        return True

    token = await create_password_reset_token(user.id)
    reset_url = f"{settings.app_url}/reset-password?token={token}"

    try:
        from grunt.email.service import email_service

        html_body = await grunt.render_template(
            "password_reset.html",
            {"full_name": user.full_name, "reset_url": reset_url},
        )
        plain = (
            f"Привіт, {user.full_name}.\n\n"
            "Посилання для скидання пароля (дійсне 1 годину):\n\n"
            f"{reset_url}\n\n"
            "Якщо ви не надсилали цей запит — проігноруйте цей лист."
        )
        session = require_session()
        await email_service.queue_email(
            session=session,
            to=user.email,
            subject="Скидання пароля",
            body=plain,
            html_body=html_body,
        )
        await session.flush()
        log.info("auth.forgot_password", email=user.email)
    except Exception:
        log.warning("auth.forgot_password_email_queue_failed", email=user.email)

    return True


@grunt.whitelist(allow_guest=True)
async def reset_password_api(token: str, new_password: str) -> bool:
    """Reset password using a valid reset token."""
    from grunt.auth.password_policy import enforce_password_policy
    from grunt.auth.service import consume_password_reset_token

    await enforce_password_policy(new_password)

    reset_ok = await consume_password_reset_token(token, new_password)
    if not reset_ok:
        grunt.throw("Invalid or expired reset token", "VALIDATION_ERROR")
    return True
