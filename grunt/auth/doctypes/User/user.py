"""User DocType controller - validation, self-edit guard, built-in identities.

Account services (lookups, lockout) live in ``grunt.auth.users``, password
hashing in ``grunt.auth.passwords``, the HTTP endpoints in
``grunt.auth.user_api`` (method paths ``grunt.auth.user_api.<name>``).
JWT access tokens live in ``grunt.auth.service``; per-device sessions and their
refresh tokens in ``grunt.auth.doctypes.UserSession``.
"""

import re as _re
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from typing import Any

from grunt.auth.constants import GUEST_USER_EMAIL, SYSTEM_USER_EMAIL
from grunt.auth.doctypes.RoleProfile.role_profile import with_profile_roles
from grunt.auth.doctypes.UserRole.user_role import ROLE_ROW_FIELDS, plain_role_row
from grunt.auth.password_policy import enforce_password_policy
from grunt.auth.passwords import hash_password, verify_password
from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.document.schema import Schema
from grunt.errors import throw
from grunt.i18n import N_, _
from grunt.local import _user_ctx, active_role_rows, use_system_user
from grunt.log import log
from grunt.permissions.perms import has_perm

_db = GruntDB()  # stateless: reads through the context's session

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
    password_changed_at: datetime | None  # Password changed
    login_after: time | None  # Sign in from
    login_before: time | None  # Sign in until
    allowed_ips: str | None  # Allowed IP addresses
    storage_quota_mb: int | None  # Personal space quota, MB
    mfa_enabled: bool | None  # MFA enabled
    mfa_secret: str | None  # MFA secret
    mfa_backup_codes: dict | None  # Backup code hashes
    mfa_backup_display: str | None  # Backup codes
    login_attempts: int | None  # Failed login attempts
    locked_until: datetime | None  # Account locked until
    theme: str | None  # Theme
    language: str | None  # Language
    notification_digest: str | None  # Email digest
    follow_created: bool | None  # Follow documents I create
    follow_commented: bool | None  # Follow documents I comment on
    follow_assigned: bool | None  # Follow documents assigned to me
    follow_shared: bool | None  # Follow documents shared with me
    reset_token: str | None  # Password reset token
    reset_token_expires_at: datetime | None  # Reset token expiry
    role_profiles: list[dict]  # Table: UserRoleProfile
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
        rows = self.data.get("role_rows")
        if rows is None:
            rows = self.data.get("roles") or []
        return list(dict.fromkeys(r["role_name"] for r in active_role_rows(rows)))

    def has_role(self, *roles: str) -> bool:
        """True if the user holds any of *roles*."""
        return any(r in roles for r in self.role_names)

    async def validate(self) -> None:
        if not self.email:
            raise ValueError(_("Email is required"))
        if not self.first_name:
            raise ValueError(_("First name is required"))
        if not self.last_name:
            raise ValueError(_("Last name is required"))
        if "roles" in self.data:
            _validate_role_rows(self.data.get("roles") or [])
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
        current = _user_ctx.get()
        if current is None or not getattr(current, "id", None):
            return
        if await has_perm("grunt.manage_users", user=current.email):
            return
        if await _is_internal_context():
            return
        if not self.name:
            throw(_("Not permitted to create users"), "FORBIDDEN")

        # Roles are only in the merged payload when the client actually submitted
        # the child table (see the update pipeline) - so key presence == an attempt.
        if "roles" in self.data:
            # The whole assignment counts - a scope or a period is as much a
            # privilege as the role itself, and so is where it came from: a
            # row taken off its profile would outlive the profile.
            stored = await _db.get_all(
                "UserRole",
                filters={"parent_name": self.name, "parent_doctype": "User"},
                fields=[*ROLE_ROW_FIELDS, "role_profile"],
                limit=500,
            )
            submitted = [r for r in (self.data.get("roles") or []) if isinstance(r, dict)]
            if _assignments(submitted) != _assignments(stored):
                throw(_("Not permitted to change roles"), "FORBIDDEN")
        if "role_profiles" in self.data and set(
            _profile_names(self.data.get("role_profiles"))
        ) != set(await self._stored_profiles()):
            throw(_("Not permitted to change roles"), "FORBIDDEN")

        # Framework-managed fields the form only echoes back - quietly restore
        # the stored value rather than failing the save.
        for field in _SILENT_RESET_USER_FIELDS:
            if field in self.data:
                self.data[field] = await _db.get_value("User", self.name, field)

        # User-meaningful privileged fields - changing one is an escalation
        # attempt: reject and say exactly which field.
        for field, label in _GUARDED_USER_FIELDS.items():
            if field not in self.data:
                continue
            if field == "password":
                if self.data.get("password"):
                    throw(
                        _("Not permitted to set the password; use the Change password action"),
                        "FORBIDDEN",
                    )
                continue
            stored = await _db.get_value("User", self.name, field)
            if _norm_scalar(self.data.get(field)) != _norm_scalar(stored):
                throw(
                    _("Not permitted to change the field “%(field)s”") % {"field": _(label)},
                    "FORBIDDEN",
                )

    async def before_save(self) -> None:
        """Construct full_name from components."""
        parts = [self.last_name, self.first_name, self.middle_name]
        self.full_name = " ".join([p.strip() for p in parts if p and p.strip()])
        await self._publish_avatar_file()
        await self._apply_role_profiles()

    async def _apply_role_profiles(self) -> None:
        """Rebuild the roles copied from the user's profiles (``UserRole.role_profile``)
        whenever the roles or the profiles are saved."""
        if "roles" not in self.data and "role_profiles" not in self.data:
            return
        if "role_profiles" in self.data:
            profiles = _profile_names(self.data.get("role_profiles"))
        else:
            profiles = await self._stored_profiles()
        if "roles" in self.data:
            roles = list(self.data.get("roles") or [])
        elif self.name:
            roles = await _db.get_all(
                "UserRole",
                filters={"parent_name": self.name, "parent_doctype": "User"},
                fields=[*ROLE_ROW_FIELDS, "role_profile"],
                limit=500,
                order_by="idx",
                order="asc",
            )
        else:
            roles = []
        rebuilt = await with_profile_roles(roles, profiles)
        if "roles" in self.data or rebuilt != roles:
            self.data["roles"] = rebuilt

    async def _stored_profiles(self) -> list[str]:
        if not self.name:
            return []
        return await _db.get_all(
            "UserRoleProfile",
            filters={"parent_name": self.name, "parent_doctype": "User"},
            pluck="role_profile",
            limit=None,
            order_by="idx",
            order="asc",
        )

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
            row = await _db.get_values("File", file_id, ["owner", "is_public"])
            if not row:
                return
            # SECURITY: publish ONLY a file the saving user owns. Without this an
            # attacker could set their own avatar to someone else's private
            # file_id and flip it world-readable (IDOR) - re-opening the very
            # signed-URL protection this hook relies on.
            if row.get("owner") != self.name:
                return
            if not row.get("is_public"):
                await _db.set_value("File", file_id, "is_public", True)
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
            self.data["password_changed_at"] = datetime.now(UTC)
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
        "email": SYSTEM_USER_EMAIL,
        "full_name": "System",
        "roles": ["System Manager"],
        "is_active": True,
        "theme": "system",
        "language": "uk",
    },
)
use_system_user(SYSTEM_USER)


# Anonymous visitors of the public site (form submissions, uploads) act as
# this identity - the Guest role's permissions only.
GUEST_USER = GUEST_USER_EMAIL


def guest_user() -> User:
    return User(
        doctype="User",
        data={"email": GUEST_USER, "full_name": "Guest", "roles": ["Guest"], "is_active": True},
    )


def _profile_names(rows: Any) -> list[str]:
    """Profile names of ``role_profiles`` rows, in order, each once."""
    names = [r.get("role_profile") for r in rows or [] if isinstance(r, dict)]
    return list(dict.fromkeys(n for n in names if n))


def _assignments(rows: Sequence[dict[str, Any]]) -> list[tuple[str, ...]]:
    """Role assignment rows compared as a set (order and row ids don't matter),
    with the profile each came from."""
    return sorted(
        (*(str(v or "") for v in plain_role_row(r).values()), str(r.get("role_profile") or ""))
        for r in rows
    )


def _validate_role_rows(rows: list[Any]) -> None:
    """A scope names both the DocType and the record; a period ends after it starts."""
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = row.get("role_name") or ""
        if bool(row.get("scope_doctype")) != bool(row.get("scope_value")):
            throw(
                _("Role “%(role)s”: a scope needs both the document type and the document")
                % {"role": _(role)},
                "VALIDATION_ERROR",
            )
        start, end = row.get("valid_from"), row.get("valid_to")
        if start and end and str(end)[:10] < str(start)[:10]:
            throw(
                _("Role “%(role)s”: “Valid to” is before “Valid from”") % {"role": _(role)},
                "VALIDATION_ERROR",
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
    current = _user_ctx.get()
    return not current or current.email == SYSTEM_USER.email
