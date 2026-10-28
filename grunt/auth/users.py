"""User accounts service - password hashing, lookups, creation, sign-in lockout.

The User DocType controller lives in ``grunt.auth.doctypes.User.user`` and the
HTTP endpoints in ``grunt.auth.user_api``; both re-export what they need from
here. Everything is still importable from ``grunt.auth.doctypes.User.user``.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import anyio.to_thread
import bcrypt

import grunt
from grunt import _, log
from grunt.auth.doctypes.UserRole.user_role import get_user_roles
from grunt.config import settings
from grunt.permissions.roles import user_has_roles
from grunt.site.manager import site_manager
from grunt.site.settings import get_setting
lazy from grunt.auth.doctypes.Role.role import Role
lazy from grunt.auth.doctypes.User.user import SYSTEM_USER, User

_MAX_ATTEMPTS = 10
_LOCKOUT_MINUTES = 30

# Columns needed to authorize and identify an already-logged-in user on an
# ordinary request (see grunt.auth.dependencies.current_user/optional_user).
# Deliberately excludes password/token/MFA-secret columns - those only ever
# matter during login, password-reset, or MFA setup, which fetch the user
# themselves via get_user_by_email/get_user_by_id without this restriction.
AUTH_CONTEXT_FIELDS: list[str] = [
    "name",
    "owner",
    "created_at",
    "modified_at",
    "modified_by",
    "first_name",
    "last_name",
    "middle_name",
    "full_name",
    "avatar",
    "email",
    "phone",
    "birth_date",
    "gender",
    "timezone",
    "bio",
    "is_active",
    "signup_state",
    "mfa_enabled",
    "theme",
    "language",
    "last_login",
]


# Password helpers


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


# User CRUD


async def _get_user_by(fields: list[str] | None = None, **filter_kwargs: str) -> User | None:
    """Look up a user by a single field (email or name). Runs as SYSTEM_USER -
    needed pre-login, when no real user is in context yet.

    ``fields`` restricts the SELECT to those columns (see ``AUTH_CONTEXT_FIELDS``);
    omit it to fetch the full row, including password/token/MFA columns.
    """
    session = grunt.get_session()
    async with grunt.system_context(session):
        query = User.objects.filter(**filter_kwargs)
        if fields is not None:
            query = query.only(*fields)
        user = await query.first()
        if user is None:
            return None
        user.data["roles"] = await get_user_roles(user.name)
        return user


async def get_user_by_email(email: str, *, fields: list[str] | None = None) -> User | None:
    """Look up a user by email. See :func:`_get_user_by`."""
    return await _get_user_by(fields, email=email)


async def get_users_by_emails(emails: list[str], *, fields: list[str] | None = None) -> list[User]:
    """Batch lookup by email - one query instead of N :func:`get_user_by_email` calls.

    Unlike :func:`get_user_by_email`, this does not attach ``roles`` (not
    needed by its current callers, e.g. the sidebar's people list).
    """

    if not emails:
        return []

    session = grunt.get_session()
    async with grunt.system_context(session):
        query = User.objects.filter(email__in=emails)
        if fields is not None:
            query = query.only(*fields)
        return await query.all()


async def get_user_by_id(user_id: str, *, fields: list[str] | None = None) -> User | None:
    """Look up a user by id. See :func:`_get_user_by`."""
    return await _get_user_by(fields, name=user_id)


async def get_auth_context_user(uid: str) -> User | None:
    """Resolve the authenticated user for request context - email/is_active/roles
    plus display profile fields (``AUTH_CONTEXT_FIELDS``).

    Used by :func:`grunt.auth.dependencies.current_user`/``optional_user`` on
    (almost) every request, so this goes through ``grunt.doc_cache`` (a
    generic per-document cache, see ``grunt/cache/document_cache.py``) instead
    of hitting the DB each time. The cache is invalidated on every ``User``
    write (see ``DocumentAPI._invalidate_list_cache``), so a role change or
    deactivation still takes effect on the very next request - a cache hit is
    never more than that stale-write race, not a TTL.
    """
    if not settings.doc_cache_enabled:
        return await get_user_by_id(uid, fields=AUTH_CONTEXT_FIELDS)

    cached = await grunt.doc_cache.get("User", uid)
    if cached is not None:
        return User(
            doctype="User", data=dict(cached), user=SYSTEM_USER, session=grunt.get_session()
        )

    user = await get_user_by_id(uid, fields=AUTH_CONTEXT_FIELDS)
    if user is not None:
        await grunt.doc_cache.set("User", uid, dict(user.data))
    return user


async def list_users() -> list[User]:
    """List all users. Runs as SYSTEM_USER - callers (CLI, admin API) gate access
    themselves before calling this."""
    session = grunt.get_session()
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
    """Create a new user. The first user automatically gets the "System Manager" role."""
    session = grunt.get_session()
    engine = site_manager.get_engine(site_manager.get_active_site())
    async with grunt.system_context(session, engine):
        is_first_user = await User.objects.count() == 0
        await User.objects.create(
            email=email,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            password=password,
            is_active=True,
        )
        if is_first_user:
            await _grant_system_manager(email)
        log.info("user.created", email=email, first_user=is_first_user)

    user = await get_user_by_email(email)
    assert user is not None
    return user


async def _grant_system_manager(user_id: str) -> None:
    """Ensure the "System Manager" role exists and assign it to *user_id* -
    used to make the first user on a site an administrator."""
    if not await grunt.db.exists("Role", {"role_name": "System Manager"}):
        await Role.objects.create(role_name="System Manager")
    await grunt.save_doc("User", user_id, {"roles": [{"role_name": "System Manager"}]})


# Sign-in lockout


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
    max_attempts = int(await get_setting("max_login_attempts", _MAX_ATTEMPTS) or _MAX_ATTEMPTS)
    lockout_minutes = int(
        await get_setting("account_lockout_duration", _LOCKOUT_MINUTES) or _LOCKOUT_MINUTES
    )
    assert user.name
    session = grunt.get_session()
    async with grunt.system_context(session):
        # Fresh count, not the copy loaded at the start of the request.
        stored = await grunt.db.get_value("User", user.name, "login_attempts")
        new_attempts = int(stored or 0) + 1
        updates: dict = {"login_attempts": new_attempts}
        if new_attempts >= max_attempts:
            updates["locked_until"] = datetime.now(UTC) + timedelta(minutes=lockout_minutes)
            updates["login_attempts"] = 0
        await grunt.db.set_value("User", user.name, updates)
    # Persist now: the caller rejects the sign-in by raising, and the request
    # session is rolled back on an exception - which would otherwise undo this
    # counter and leave guessing unlimited. Only ever called from an auth
    # *failure* path (login / MFA), which holds no other pending writes to
    # flush - so committing the request session here discards nothing else.
    await session.commit()


async def clear_failed_attempts(user: User) -> None:
    """Reset the failed-sign-in counter and any lock after a success."""

    assert user.name
    async with grunt.system_context(grunt.get_session()):
        await grunt.db.set_value("User", user.name, {"login_attempts": 0, "locked_until": None})


async def authenticate(email: str, password: str) -> User | None:
    """Return user if credentials are valid, else None.

    Tracks failed attempts and locks the account after ``max_login_attempts``
    (``SystemSettings``) failures for ``account_lockout_duration`` minutes.
    Raises ``ValueError("locked")`` when the account is temporarily locked.
    """

    user = await get_user_by_email(email)
    if user is None:
        return None

    if await is_account_locked(user):
        raise ValueError("locked")

    async with grunt.system_context(grunt.get_session()):
        valid = bool(user.hashed_password) and await verify_password(password, user.hashed_password)

    if not valid:
        await register_failed_attempt(user)
        return None

    # NB: the counter is cleared in issue_login (full-login completion), not
    # here - a password success that still owes an MFA code must not reset the
    # lockout that guards the second factor.
    return user


def _auth_user_dump(user: User) -> dict[str, Any]:
    """Full user payload expected by auth UI responses."""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": user.roles,
        "theme": user.theme,
        "avatar": user.avatar,
        "mfa_enabled": bool(user.mfa_enabled),
        "has_password": bool(user.hashed_password),
        "language": getattr(user, "language", None) or None,
        "timezone": getattr(user, "timezone", None) or None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# Self-service registration


async def _guard_registration() -> None:
    """Block self-service registration unless ``allow_user_registration`` is on.

    The very first user is always allowed - that path is the setup wizard /
    ``grunt site create`` bootstrap, not public sign-up.
    """
    if await grunt.db.count("User") == 0:
        return
    if not await get_setting("allow_user_registration", False):
        grunt.throw(_("Registration of new users is disabled"), "FORBIDDEN")


async def _assign_default_role(user_id: str | None) -> None:
    """Give a freshly registered user the configured ``default_role`` (if any).

    Runs as SYSTEM - registration happens in a guest context that cannot
    write the admin-only ``User.roles`` table.
    """
    role = await get_setting("default_role")
    if not role or not user_id:
        return

    async with grunt.system_context(grunt.get_session()):
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
    approves them. System Manager (the bootstrap first user) is never held.

    Returns True when the user was left pending.
    """
    if user_has_roles(user, ["System Manager"]) or not await get_setting(
        "require_signup_approval", False
    ):
        return False

    assert user.id is not None
    async with grunt.system_context(grunt.get_session()):
        await grunt.db.set_value("User", user.id, {"signup_state": "pending", "is_active": False})
    user.data["signup_state"] = "pending"
    user.data["is_active"] = False
    log.info("user.pending_approval", email=user.email)
    return True
