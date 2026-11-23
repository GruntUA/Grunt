"""Role DocType controller."""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.permissions.perms import ALL, get_perm, user_perms
from grunt.permissions.role_props import PROTECTED_ROLES, invalidate_roles
from grunt.site.manager import site_cache_key
lazy from grunt.document.api import documents


class Role(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    role_name: str  # Name
    description: str | None = None  # Description
    disabled: bool | None = None  # Disabled
    site_only: bool | None = None  # Site only
    home_page: str | None = None  # Home page
    permissions: list[str] | None = None  # Permissions
    require_mfa: bool | None = None  # Require two-factor authentication
    allowed_ips: str | None = None  # Allowed sign-in IPs

    # end: auto-generated types

    """DocType controller for Role."""

    role_name: str
    description: str | None
    permissions: list[str] | None

    async def validate(self) -> None:
        if self.name in PROTECTED_ROLES and (self.disabled or self.site_only):
            throw(
                _("The role “%(role)s” can't be disabled or made site-only") % {"role": self.name},
                "VALIDATION_ERROR",
            )
        home = (self.home_page or "").strip()
        if home and (
            not home.startswith("/")
            or home.startswith("//")
            or any(c.isspace() or c == "\\" or not c.isprintable() for c in home)
        ):
            throw(_("Home page must be a path on this site, starting with /"), "VALIDATION_ERROR")
        self.home_page = home or None

        granted = list(dict.fromkeys(self.permissions or []))
        unknown = [p for p in granted if p != ALL and get_perm(p) is None]
        if unknown:
            throw(
                _("Unknown permissions: %(perms)s") % {"perms": ", ".join(unknown)},
                "VALIDATION_ERROR",
            )
        self.permissions = granted

        # Nobody hands out more than they hold: a permission newly added to a
        # role must be one the editor holds themselves.
        before = set((self.doc_before_save or {}).get("permissions") or [])
        added = [p for p in granted if p not in before]
        if added:
            held = await user_perms()
            missing = [p for p in added if ALL not in held and p not in held]
            if missing:
                throw(
                    _("You can't grant permissions you don't hold: %(perms)s")
                    % {"perms": ", ".join(missing)},
                    "FORBIDDEN",
                )

    async def after_save(self) -> None:
        invalidate_roles(site_cache_key())
        before = self.doc_before_save or {}
        if bool(before.get("disabled")) != bool(self.disabled):
            # Signed-in users carry their roles in the cached User: drop it so
            # disabling (or enabling) takes effect on their next request.
            await documents.doc_cache.invalidate_doctype("User")

    async def after_delete(self) -> None:
        invalidate_roles(site_cache_key())
