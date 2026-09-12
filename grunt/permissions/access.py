"""Role-based access facts for a (doctype, user) pair.

`PermissionChecker.check()`/`.hidden_fields()` (rbac.py) and
`apply_permission_filter()` (query.py) each independently re-derived the same
two things: whether access checks apply at all (superadmin bypasses
everything), and which `DocPermission` rows a user's roles actually
match. Wrapping that here means the three call sites can't drift the way
`PermissionMatch`'s two evaluation modes already had.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType
    from grunt.metadata.permission import DocPermission


class RoleAccess:
    """Role-based access facts for *user* on *doctype*, computed once."""

    def __init__(self, doctype: DocType, user: User) -> None:
        self.doctype = doctype
        self.user = user
        self.user_roles: frozenset[str] = frozenset(getattr(user, "roles", []) or [])

    @property
    def has_unrestricted_read(self) -> bool:
        """True when a matching permission grants ``read`` with no row ``match`` —
        the user may read every row, not just a filtered subset.

        ``apply_permission_filter()`` and the Link/tree picker gates both need to
        tell "reads everything" apart from "reads only rows matching an
        expression"; ``check(user, dt, "read")`` can't, because with ``doc=None``
        it skips ``match`` and answers True for a row-scoped grant too.
        """
        if self.is_unrestricted:
            return True
        return any(
            getattr(perm, "read", False) and not getattr(perm, "match", None)
            for perm in self.matching_permissions()
        )

    @property
    def has_explicit_select(self) -> bool:
        """True when a matching permission sets ``select`` explicitly (not merely
        implied by ``read``).

        The Link-picker / tree-picker identifier path checks this to offer an
        unfiltered identifier search even when the user's only ``read`` grant is
        row-scoped: ``match`` is irrelevant there because that path resolves
        identifier columns only and never applies row-level filters.
        """
        if self.is_unrestricted:
            return True
        return any(getattr(perm, "select", False) for perm in self.matching_permissions())

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

    def matching_permissions(self) -> list[DocPermission]:
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
    def _role_of(perm: DocPermission) -> str:
        return perm.role if hasattr(perm, "role") else ""
