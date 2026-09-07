"""User DocType controller — password hashing, authentication, and user CRUD.

All business logic related to the User document lives here.
The auth layer (JWT tokens, refresh tokens) remains in ``grunt.core.auth.service``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import anyio.to_thread
import bcrypt
import structlog

if TYPE_CHECKING:
    from fastapi import Request

import grunt
from grunt.document.base import Document
from grunt.document.schema import Schema

logger = structlog.get_logger()

_MAX_ATTEMPTS = 10
_LOCKOUT_MINUTES = 30

# When a non-privileged user saves their *own* record via the generic form (the
# "All" permission row lets them), these fields must not change. Roles live in
# the `roles` child table and are guarded separately. Privileged callers
# (System Manager / superadmin) and internal/system code bypass this.
#
# Two tiers:
#  * _GUARDED — user-meaningful privileged fields; changing one is a real
#    escalation attempt, so reject loudly and name the field.
#  * _SILENT_RESET — framework-managed / read-only fields the form just echoes
#    back; a stale echo is not an attack, so quietly restore the stored value
#    instead of failing the whole save.
_GUARDED_USER_FIELDS: dict[str, str] = {
    "email": "Email",  # autoname source — renaming an account is an admin action
    "is_active": "Активний",
    "is_superadmin": "Суперадмін",
    "signup_state": "Стан реєстрації",
    "password": "Пароль",
}
_SILENT_RESET_USER_FIELDS: frozenset[str] = frozenset(
    {
        "hashed_password",
        "mfa_enabled",
        "mfa_secret",
        "mfa_backup_codes",
        "login_attempts",
        "locked_until",
        "last_login",
        "refresh_token",
        "refresh_token_expires_at",
        "reset_token",
        "reset_token_expires_at",
    }
)

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
    signup_state: str
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
        await self._enforce_self_edit_scope()

    async def _enforce_self_edit_scope(self) -> None:
        """Restrict what a non-privileged user may change on their own record.

        The ``{"role": "All", "match": "name == user"}`` permission on User lets
        any authenticated user save *their own* profile via the generic form.
        This keeps that to profile fields only — roles, activation, superadmin,
        password and MFA state stay admin-only. System Manager / superadmin and
        internal/system code (registration, fixtures, ``_assign_default_role``)
        are unrestricted.
        """
        from grunt.permissions.roles import user_has_roles

        try:
            current = await grunt.get_current_user()
        except Exception:
            return
        if current is None or not getattr(current, "id", None):
            return
        if user_has_roles(current, ["System Manager"]):  # True for superadmin too
            return
        if await _is_internal_context():
            return
        if not self.name:
            grunt.throw("Недостатньо прав для створення користувача", "FORBIDDEN")

        # Roles are only in the merged payload when the client actually submitted
        # the child table (see update_document) — so key presence == an attempt.
        if "roles" in self.data:
            stored = await grunt.db.get_all(
                "UserRole",
                filters={"parent_name": self.name, "parent_doctype": "User"},
                fields=["role_name"],
                limit=100,
            )
            submitted = {
                r.get("role_name")
                for r in (self.data.get("roles") or [])
                if isinstance(r, dict)
            }
            if submitted != {r["role_name"] for r in stored}:
                grunt.throw("Недостатньо прав для зміни ролей", "FORBIDDEN")

        # Framework-managed fields the form only echoes back — quietly restore
        # the stored value rather than failing the save.
        for field in _SILENT_RESET_USER_FIELDS:
            if field in self.data:
                self.data[field] = await grunt.db.get_value("User", self.name, field)

        # User-meaningful privileged fields — changing one is an escalation
        # attempt: reject and say exactly which field.
        for field, label in _GUARDED_USER_FIELDS.items():
            if field not in self.data:
                continue
            if field == "password":
                if self.data.get("password"):
                    grunt.throw(
                        "Недостатньо прав, щоб задати пароль — скористайтесь дією «Змінити пароль»",
                        "FORBIDDEN",
                    )
                continue
            stored = await grunt.db.get_value("User", self.name, field)
            if _norm_scalar(self.data.get(field)) != _norm_scalar(stored):
                grunt.throw(f"Недостатньо прав, щоб змінити поле «{label}»", "FORBIDDEN")

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


def _norm_scalar(value: Any) -> str:
    """Loose scalar comparison key for _enforce_self_edit_scope — treats
    None / "" / whitespace as equal and compares everything else by string."""
    if value is None:
        return ""
    return str(value).strip()


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


async def is_account_locked(user: User) -> bool:
    """True while ``user.locked_until`` is still in the future."""
    if not user.locked_until:
        return False
    locked_until = user.locked_until
    if locked_until.tzinfo is not None and locked_until.utcoffset() is not None:
        locked_until = locked_until.astimezone(UTC)
    else:
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > datetime.now(UTC)


async def register_failed_attempt(user: User) -> None:
    """Count one failed sign-in; lock the account past ``max_login_attempts``
    (``SystemSettings``) for ``account_lockout_duration`` minutes.

    Shared by every authentication factor (password, email code, ...).
    """
    from grunt.context import require_session
    from grunt.site.settings import get_setting

    max_attempts = int(await get_setting("max_login_attempts", _MAX_ATTEMPTS) or _MAX_ATTEMPTS)
    lockout_minutes = int(
        await get_setting("account_lockout_duration", _LOCKOUT_MINUTES) or _LOCKOUT_MINUTES
    )
    new_attempts = (user.login_attempts or 0) + 1
    updates: dict = {"login_attempts": new_attempts}
    if new_attempts >= max_attempts:
        updates["locked_until"] = datetime.now(UTC) + timedelta(minutes=lockout_minutes)
        updates["login_attempts"] = 0
    async with grunt.system_context(require_session()):
        await grunt.db.set_value("User", user.name, updates)


async def clear_failed_attempts(user: User) -> None:
    """Reset the failed-sign-in counter and any lock after a success."""
    from grunt.context import require_session

    async with grunt.system_context(require_session()):
        await grunt.db.set_value("User", user.name, {"login_attempts": 0, "locked_until": None})


async def authenticate(email: str, password: str) -> User | None:
    """Return user if credentials are valid, else None.

    Tracks failed attempts and locks the account after ``max_login_attempts``
    (``SystemSettings``) failures for ``account_lockout_duration`` minutes.
    Raises ``ValueError("locked")`` when the account is temporarily locked.
    """
    from grunt.context import require_session

    user = await get_user_by_email(email)
    if user is None:
        return None

    if await is_account_locked(user):
        raise ValueError("locked")

    async with grunt.system_context(require_session()):
        valid = bool(user.hashed_password) and await verify_password(
            password, user.hashed_password
        )

    if not valid:
        await register_failed_attempt(user)
        return None

    await clear_failed_attempts(user)
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
        "has_password": bool(user.hashed_password),
        "language": getattr(user, "language", None) or None,
        "timezone": getattr(user, "timezone", None) or None,
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
    """Give a freshly registered user the configured ``default_role`` (if any).

    Runs as SYSTEM — registration happens in a guest context that cannot
    write the admin-only ``User.roles`` table.
    """
    from grunt.context import require_session
    from grunt.site.settings import get_setting

    role = await get_setting("default_role")
    if not role or not user_id:
        return

    async with grunt.system_context(require_session()):
        if not await grunt.db.exists("Role", {"role_name": role}):
            return
        current = await grunt.db.get_all(
            "UserRole",
            filters={"parent_name": user_id, "parent_doctype": "User"},
            fields=["role_name"],
            limit=100,
        )
        names = {r["role_name"] for r in current}
        if role in names:
            return
        rows = [{"role_name": n} for n in names] + [{"role_name": role}]
        await grunt.save_doc("User", user_id, {"roles": rows})


async def _apply_signup_approval(user: User) -> bool:
    """Put a freshly self-registered user in the ``pending`` state when
    ``require_signup_approval`` is on, so they can't sign in until an admin
    approves them. Superadmins (the bootstrap first user) are never held.

    Returns True when the user was left pending.
    """
    from grunt.context import require_session
    from grunt.site.settings import get_setting

    if user.is_superadmin or not await get_setting("require_signup_approval", False):
        return False

    assert user.id is not None
    async with grunt.system_context(require_session()):
        await grunt.db.set_value(
            "User", user.id, {"signup_state": "pending", "is_active": False}
        )
    user.data["signup_state"] = "pending"
    user.data["is_active"] = False
    logger.info("user.pending_approval", email=user.email)
    return True


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
    pending = await _apply_signup_approval(user)
    return {**UserPublic.dump(user), "approval_pending": pending}


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
    pending = await _apply_signup_approval(user)
    return {**_auth_user_dump(user), "approval_pending": pending}


@grunt.whitelist(allow_guest=True)
async def login_api(
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Authenticate a user and issue auth tokens or MFA challenge token."""
    from grunt.auth.login import issue_login

    try:
        user = await authenticate(email, password)
    except ValueError as exc:
        if str(exc) == "locked":
            grunt.throw("Account temporarily locked. Try again later.", "TOO_MANY_REQUESTS")
        raise

    if user is None:
        grunt.throw("Incorrect email or password", "UNAUTHORIZED")

    return await issue_login(user, ip_address=ip_address, user_agent=user_agent)


@grunt.whitelist(allow_guest=True)
async def mfa_login_api(
    mfa_token: str,
    code: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Verify MFA challenge token+code and issue full auth tokens."""
    from grunt.auth.login import issue_login
    from grunt.auth.mfa import check_mfa_code
    from grunt.auth.service import verify_mfa_token

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

    # honor_mfa=False: the second factor has just been proven here.
    return await issue_login(
        user, ip_address=ip_address, user_agent=user_agent, honor_mfa=False
    )


@grunt.whitelist()
async def whoami() -> dict[str, Any]:
    """Return the currently authenticated user.

    Re-reads the row from the DB (the context user is built from JWT claims and
    lacks profile fields like ``mfa_enabled`` / ``language`` / ``timezone``).
    """
    ctx_user = await grunt.get_current_user()
    user = (await get_user_by_id(ctx_user.id) if ctx_user.id else None) or ctx_user
    return {
        **UserPublic.dump(user),
        "mfa_enabled": bool(user.mfa_enabled),
        "has_password": bool(getattr(user, "hashed_password", None)),
        "language": getattr(user, "language", None) or None,
        "timezone": getattr(user, "timezone", None) or None,
        # Set only while a superadmin is viewing the system as this user.
        "impersonated_by": ctx_user.data.get("_impersonator"),
    }


@grunt.whitelist()
async def me_api() -> dict[str, Any]:
    """Return current user with the full auth payload fields."""
    user = await grunt.get_current_user()
    return _auth_user_dump(user)


@grunt.whitelist()
async def update_me_api(
    theme: str | None = None,
    language: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Update current user preferences and return updated profile."""
    user = await grunt.get_current_user()

    values: dict[str, Any] = {}
    if theme is not None:
        if theme not in ("light", "dark", "system"):
            grunt.throw("Invalid theme value", "VALIDATION_ERROR")
        values["theme"] = theme
    if language is not None:
        if language not in ("uk", "en"):
            grunt.throw("Invalid language value", "VALIDATION_ERROR")
        values["language"] = language
    if timezone is not None:
        values["timezone"] = timezone.strip()

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


@grunt.whitelist(require=lambda user: bool(user.is_superadmin))
async def start_impersonation_api(user_id: str) -> dict[str, Any]:
    """Open a short-lived session as another user. Superadmin only.

    Returns an access token (no refresh token) that authenticates as
    ``user_id`` with that user's roles, plus an ``impersonated_by`` block.
    """
    from grunt.auth.impersonation import start_impersonation

    actor = await grunt.get_current_user()
    return await start_impersonation(actor, user_id)


@grunt.whitelist()
async def stop_impersonation_api() -> bool:
    """Log the end of an impersonation session.

    The real session is restored client-side from the tokens it stashed before
    starting; this endpoint only records that the view-as session was closed.
    """
    user = await grunt.get_current_user()
    imp = user.data.get("_impersonator") if hasattr(user, "data") else None
    if imp:
        logger.warning(
            "auth.impersonation.stop",
            actor=imp.get("email"),
            target=user.email,
        )
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
            "is_active": bool(u.is_active),
            "signup_state": getattr(u, "signup_state", None) or "approved",
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@grunt.whitelist(roles=["superadmin"])
async def list_pending_users_api() -> list[dict[str, Any]]:
    """Self-registered users awaiting approval. Superadmin only."""
    rows = await grunt.get_list(
        "User",
        filters={"signup_state": "pending"},
        fields=["name", "email", "full_name", "created_at"],
        order_by="created_at asc",
        limit=500,
    )
    return rows


async def _set_signup_state(user_id: str, state: str) -> bool:
    user = await get_user_by_id(user_id)
    if not user or not user.id:
        grunt.throw("Користувача не знайдено", "NOT_FOUND")
    await grunt.set_value(
        "User",
        user.id,
        {"signup_state": state, "is_active": state == "approved"},
    )
    logger.info("user.signup_state_changed", email=user.email, state=state)
    return True


@grunt.whitelist(roles=["superadmin"])
async def approve_user_api(user_id: str) -> bool:
    """Approve a pending registration — the user can now sign in. Superadmin only."""
    return await _set_signup_state(user_id, "approved")


@grunt.whitelist(roles=["superadmin"])
async def reject_user_api(user_id: str) -> bool:
    """Reject a pending registration. Superadmin only."""
    return await _set_signup_state(user_id, "rejected")


@grunt.whitelist()
async def set_user_password_api(
    user_id: str, new_password: str, current_password: str | None = None
) -> bool:
    """Set a new password for a user.

    A user may change *their own* password by passing their ``current_password``.
    When the account has no password yet (provisioned via OIDC / email link),
    that check is skipped — it is a first-time set. Changing *someone else's*
    password requires System Manager / superadmin.
    """
    from grunt.auth.password_policy import enforce_password_policy
    from grunt.permissions.roles import user_has_roles

    user = await get_user_by_id(user_id)
    if not user or not user.id:
        grunt.throw("Користувача не знайдено", "NOT_FOUND")

    current = await grunt.get_current_user()
    is_self = bool(
        current
        and (
            (current.id and current.id == user.id)
            or (current.email and current.email == user.email)
        )
    )
    is_admin = bool(current and user_has_roles(current, ["System Manager"]))

    if not is_admin:
        if not is_self:
            grunt.throw(
                "Недостатньо прав, щоб змінити пароль іншого користувача", "PERMISSION_DENIED"
            )
        # A first-time set (no existing password) needs no current-password proof.
        if user.hashed_password and (
            not current_password or not await user.check_password(current_password)
        ):
            grunt.throw("Поточний пароль вказано невірно", "PERMISSION_DENIED")

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
async def forgot_password_api(email: str, request: Request | None = None) -> bool:
    """Queue a password reset email if the user exists (always returns success)."""
    import structlog

    from grunt.auth.service import create_password_reset_token
    from grunt.context import require_session
    from grunt.utils.http import public_base_url

    log = structlog.get_logger()
    user = await get_user_by_email(email)
    if user is None or not user.id:
        return True

    token = await create_password_reset_token(user.id)
    # Build the link from the caller's real origin (Host / X-Forwarded-Proto),
    # not the APP_URL default which is localhost in most deployments.
    reset_url = f"{public_base_url(request)}/reset-password?token={token}"

    try:
        from grunt.app import grunt as grunt_app
        from grunt.email.service import email_service

        html_body = await grunt_app.render_template(
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
        # Stay silent to the caller (anti-enumeration), but keep the traceback —
        # a swallowed warning here left us blind when a request landed mid-reload.
        log.warning(
            "auth.forgot_password_email_queue_failed", email=user.email, exc_info=True
        )

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
