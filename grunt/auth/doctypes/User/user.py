"""User DocType controller - validation, self-edit guard, built-in identities.

Account services (password hashing, lookups, lockout) live in
``grunt.auth.users`` and the HTTP endpoints in ``grunt.auth.user_api``. Both
are re-exported at the bottom of this module: method paths stay
``grunt.auth.doctypes.User.user.<name>`` and existing imports keep working.
JWT access tokens live in ``grunt.auth.service``; per-device sessions and their
refresh tokens in ``grunt.auth.doctypes.UserSession``.
"""

import re as _re
from datetime import date, datetime
from typing import Any

import grunt
from grunt import log
from grunt.auth.password_policy import enforce_password_policy
from grunt.auth.users import hash_password, verify_password
from grunt.document.base import Document
from grunt.document.schema import Schema
from grunt.i18n import N_, _
from grunt.permissions.roles import user_has_roles

# When a non-privileged user saves their *own* record via the generic form (the
# "All" permission row lets them), these fields must not change. Roles live in
# the `roles` child table and are guarded separately. Privileged callers
# (System Manager) and internal/system code bypass this.
#
# Two tiers:
#  * _GUARDED - user-meaningful privileged fields; changing one is a real
#    escalation attempt, so reject loudly and name the field.
#  * _SILENT_RESET - framework-managed / read-only fields the form just echoes
#    back; a stale echo is not an attack, so quietly restore the stored value
#    instead of failing the whole save.
_GUARDED_USER_FIELDS: dict[str, str] = {
    "email": N_("Email"),  # autoname source - renaming an account is an admin action
    "is_active": N_("Active"),
    "signup_state": N_("Signup state"),
    "password": N_("Password"),
    "storage_quota_mb": N_("Personal space quota, MB"),
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
        "reset_token",
        "reset_token_expires_at",
    }
)

# Document Controller


class User(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    last_name: str  # Last name
    first_name: str  # First name
    middle_name: str | None  # Patronymic
    full_name: str | None  # Full name
    avatar: str | None  # Profile photo
    email: str  # Email
    phone: str | None  # Phone
    birth_date: date | None  # Date of birth
    gender: str | None  # Gender
    timezone: str | None  # Time zone
    last_login: datetime | None  # Last login
    bio: str | None  # Short bio
    is_active: bool | None  # Active
    signup_state: str | None  # Registration state
    password: str | None  # Set password
    hashed_password: str | None  # Password hash
    storage_quota_mb: int | None  # Personal space quota, MB
    mfa_enabled: bool | None  # MFA enabled
    mfa_secret: str | None  # MFA secret
    mfa_backup_codes: dict | None  # Backup code hashes
    mfa_backup_display: str | None  # Backup codes
    login_attempts: int | None  # Failed login attempts
    locked_until: datetime | None  # Account locked until
    theme: str | None  # Theme
    language: str | None  # Language
    reset_token: str | None  # Password reset token
    reset_token_expires_at: datetime | None  # Reset token expiry
    roles: list[dict]  # Table: UserRole

    # end: auto-generated types

    """DocType controller for User.

    Handles lifecycle hooks when User documents are created or updated
    through the generic document API (form, import, etc.).
    """

    @property
    def role_names(self) -> list[str]:
        """Role names, whether ``roles`` holds the loaded names (an authenticated
        user) or the UserRole child rows (a document being saved)."""
        rows = self.data.get("roles") or []
        return [r if isinstance(r, str) else r.get("role_name", "") for r in rows]

    def has_role(self, *roles: str) -> bool:
        """True if the user holds any of *roles*."""
        return user_has_roles(self, list(roles))

    async def validate(self) -> None:
        if not self.email:
            raise ValueError(_("Email is required"))
        if not self.first_name:
            raise ValueError(_("First name is required"))
        if not self.last_name:
            raise ValueError(_("Last name is required"))
        await self._enforce_self_edit_scope()

    async def _enforce_self_edit_scope(self) -> None:
        """Restrict what a non-privileged user may change on their own record.

        The ``{"role": "All", "match": "name == user"}`` permission on User lets
        any authenticated user save *their own* profile via the generic form.
        This keeps that to profile fields only - roles, activation,
        password and MFA state stay admin-only. System Manager and
        internal/system code (registration, fixtures, ``_assign_default_role``)
        are unrestricted.
        """
        try:
            current = grunt.get_user()
        except Exception:
            return
        if current is None or not getattr(current, "id", None):
            return
        if user_has_roles(current, ["System Manager"]):
            return
        if await _is_internal_context():
            return
        if not self.name:
            grunt.throw(_("Not permitted to create users"), "FORBIDDEN")

        # Roles are only in the merged payload when the client actually submitted
        # the child table (see the update pipeline) - so key presence == an attempt.
        if "roles" in self.data:
            stored = await grunt.db.get_all(
                "UserRole",
                filters={"parent_name": self.name, "parent_doctype": "User"},
                fields=["role_name"],
                limit=100,
            )
            submitted = {
                r.get("role_name") for r in (self.data.get("roles") or []) if isinstance(r, dict)
            }
            if submitted != {r["role_name"] for r in stored}:
                grunt.throw(_("Not permitted to change roles"), "FORBIDDEN")

        # Framework-managed fields the form only echoes back - quietly restore
        # the stored value rather than failing the save.
        for field in _SILENT_RESET_USER_FIELDS:
            if field in self.data:
                self.data[field] = await grunt.db.get_value("User", self.name, field)

        # User-meaningful privileged fields - changing one is an escalation
        # attempt: reject and say exactly which field.
        for field, label in _GUARDED_USER_FIELDS.items():
            if field not in self.data:
                continue
            if field == "password":
                if self.data.get("password"):
                    grunt.throw(
                        _("Not permitted to set the password; use the Change password action"),
                        "FORBIDDEN",
                    )
                continue
            stored = await grunt.db.get_value("User", self.name, field)
            if _norm_scalar(self.data.get(field)) != _norm_scalar(stored):
                grunt.throw(
                    _("Not permitted to change the field “%(field)s”") % {"field": _(label)},
                    "FORBIDDEN",
                )

    async def before_save(self) -> None:
        """Construct full_name from components."""
        parts = [self.last_name, self.first_name, self.middle_name]
        self.full_name = " ".join([p.strip() for p in parts if p and p.strip()])
        await self._publish_avatar_file()

    async def _publish_avatar_file(self) -> None:
        """A profile photo is shown to colleagues (user pickers, comments,
        activity), so the avatar's File must be public - otherwise, now that
        file URLs are signed only for readers of the file, a user could not see
        anyone else's avatar (they cannot read another user's User row). Only
        the avatar file is published; other User attachments stay private.
        """
        avatar = self.data.get("avatar")
        if not isinstance(avatar, str) or "get_content?file_id=" not in avatar:
            return

        m = _re.search(r"get_content\?file_id=([A-Za-z0-9_-]+)", avatar)
        if not m:
            return
        file_id = m.group(1)
        try:
            row = await grunt.db.get_values("File", file_id, ["owner", "is_public"])
            if not row:
                return
            # SECURITY: publish ONLY a file the saving user owns. Without this an
            # attacker could set their own avatar to someone else's private
            # file_id and flip it world-readable (IDOR) - re-opening the very
            # signed-URL protection this hook relies on.
            if row.get("owner") != self.name:
                return
            if not row.get("is_public"):
                await grunt.db.set_value("File", file_id, "is_public", True)
        except Exception:
            # A missing/renamed file must not block saving the profile.
            log.debug("user.avatar_publish_skipped", file_id=file_id)

    async def before_insert(self) -> None:
        # If a plain-text password was passed through the generic API, hash it.
        raw = self.data.get("password")
        if raw:
            if not await _is_internal_context():
                # Interactive create (admin form / import) - hold it to policy.
                # The register_* endpoints already checked before reaching here.

                await enforce_password_policy(str(raw))
            self.hashed_password = await hash_password(str(raw))
            self.data.pop("password", None)

    async def check_password(self, plain: str) -> bool:
        """Return True if plain matches the stored hashed password."""
        return await verify_password(plain, self.hashed_password or "")


class UserPublic(Schema):
    """Fields safe to return from whoami/register/list_users_api."""

    fields = ("name", "email", "full_name", "avatar", "roles")


# Convenience system-user singleton for internal tasks. Admin rights come from
# holding the "System Manager" role, same as any other user - no special-case
# bypass for this identity.
SYSTEM_USER = User(
    doctype="User",
    data={
        "email": "system@grunt.local",
        "full_name": "System",
        "roles": ["System Manager"],
        "is_active": True,
        "theme": "system",
        "language": "uk",
    },
)


# Anonymous visitors of the public site (form submissions, uploads) act as
# this identity - the Guest role's permissions only.
GUEST_USER = "guest@grunt.local"


def guest_user() -> User:
    return User(
        doctype="User",
        data={"email": GUEST_USER, "full_name": "Guest", "roles": ["Guest"], "is_active": True},
    )


def _norm_scalar(value: Any) -> str:
    """Loose scalar comparison key for _enforce_self_edit_scope - treats
    None / "" / whitespace as equal and compares everything else by string."""
    if value is None:
        return ""
    return str(value).strip()


async def _is_internal_context() -> bool:
    """True when the active context is the internal SYSTEM_USER (bootstrap,
    fixtures, registration flows) or has no user at all - those paths must not
    be blocked by the interactive password policy."""
    try:
        current = grunt.get_user()
    except Exception:
        return True
    return not current or current.email == SYSTEM_USER.email


# Re-exports: method paths (grunt.auth.doctypes.User.user.<name>) and existing
# imports from this module keep resolving after the split.
from grunt.auth.user_api import (  # noqa: E402, F401
    approve_user_api,
    confirm_mfa,
    disable_mfa,
    forgot_password_api,
    list_colleagues_api,
    list_pending_users_api,
    list_users_detailed_api,
    login_api,
    logout_api,
    mfa_enroll_begin,
    mfa_enroll_complete,
    mfa_login_api,
    refresh_api,
    register,
    register_full_name_api,
    reject_user_api,
    reset_password_api,
    set_user_password_api,
    setup_mfa,
    start_impersonation_api,
    stop_impersonation_api,
    update_me_api,
    verify_mfa,
    whoami,
)
from grunt.auth.users import (  # noqa: E402, F401
    AUTH_CONTEXT_FIELDS,
    _apply_signup_approval,
    _auth_user_dump,
    _guard_registration,
    authenticate,
    clear_failed_attempts,
    create_user,
    get_auth_context_user,
    get_user_by_email,
    get_user_by_id,
    get_users_by_emails,
    is_account_locked,
    list_users,
    register_failed_attempt,
)
