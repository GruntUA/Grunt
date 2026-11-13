"""Role DocType controller."""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.permissions.perms import ALL, get_perm, invalidate_role_perms, user_perms
from grunt.site.manager import site_cache_key


class Role(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    role_name: str  # Name
    description: str | None  # Description
    permissions: list[str] | None  # Permissions
    require_mfa: bool | None  # Require two-factor authentication
    allowed_ips: str | None  # Allowed sign-in IPs

    # end: auto-generated types

    """DocType controller for Role."""

    role_name: str
    description: str | None
    permissions: list[str] | None

    async def validate(self) -> None:
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
        invalidate_role_perms(site_cache_key())

    async def after_delete(self) -> None:
        invalidate_role_perms(site_cache_key())
