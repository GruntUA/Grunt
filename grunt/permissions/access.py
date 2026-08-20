"""Role-based access facts for a (doctype, user) pair.

`PermissionChecker.check()`/`.hidden_fields()` (rbac.py) and
`apply_permission_filter()` (query.py) each independently re-derived the same
two things: whether access checks apply at all (superadmin bypasses
everything), and which `DocTypePermission` rows a user's roles actually
match. Wrapping that here means the three call sites can't drift the way
`PermissionMatch`'s two evaluation modes already had.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType, DocTypePermission


class RoleAccess:
    """Role-based access facts for *user* on *doctype*, computed once."""

    def __init__(self, doctype: DocType, user: User) -> None:
        self.doctype = doctype
        self.user = user
        self.user_roles: frozenset[str] = frozenset(getattr(user, "roles", []) or [])

    @property
    def is_unrestricted(self) -> bool:
        """True when access checks should be skipped entirely.

        Only superadmin bypasses. A DocType with no permission rows at all is
        closed to everyone else — "no permissions defined" means nobody has
        been granted access yet, not "open to anyone logged in". A doctype
        that should genuinely be world-readable needs an explicit
        `{"role": "All", ...}` permission row (see `matching_permissions()`).
        """
        return bool(getattr(self.user, "is_superadmin", False))

    def matching_permissions(self) -> list[DocTypePermission]:
        """Permission rows whose role applies to this user (own roles, or "All").

        Returns an empty list when :attr:`is_unrestricted` — callers must
        check that first and treat it as "everything allowed", not "nothing
        matched".
        """
        if self.is_unrestricted:
            return []
        return [
            perm
            for perm in self.doctype.permissions
            if self._role_of(perm) in self.user_roles or self._role_of(perm) == "All"
        ]

    @staticmethod
    def _role_of(perm: DocTypePermission) -> str:
        return perm.role if hasattr(perm, "role") else ""
