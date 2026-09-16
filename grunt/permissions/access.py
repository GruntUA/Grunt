"""Role-based access facts for a (doctype, user) pair.

`PermissionChecker.check()`/`.hidden_fields()` (rbac.py) and
`apply_permission_filter()` (query.py) each independently re-derived the same
thing: which `DocPermission` rows a user's roles actually match. Wrapping
that here means the three call sites can't drift the way `PermissionMatch`'s
two evaluation modes already had.

No role, including "System Manager", bypasses permission rows outright —
access is always decided by matching rows. Most DocTypes grant System
Manager unrestricted CRUD via an explicit `{"role": "System Manager", ...}`
row, but a few (read-only logs, audit trails) deliberately don't grant
write/create/delete to anyone, System Manager included — a blanket
role-based bypass would silently defeat that.

The one exception is the internal SYSTEM_USER identity (`grunt.system_context()`
— background tasks, hooks, migrations): it bypasses permission rows entirely,
same as before. That's an unrelated, non-human concern from "how do people
get admin rights" — it's what lets the framework itself write to doctypes
(like ErrorLog) that intentionally grant no write access to any real role.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.document.meta import Meta
    from grunt.metadata.doctype import DocType
    from grunt.metadata.permission import DocPermission


class RoleAccess:
    """Role-based access facts for *user* on *doctype*, computed once."""

    def __init__(self, doctype: DocType | Meta, user: User) -> None:
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
        """True only for the internal SYSTEM_USER identity — never for a human
        role, System Manager included (see module docstring)."""
        from grunt.auth.doctypes.User.user import SYSTEM_USER

        return self.user is not None and getattr(self.user, "email", None) == SYSTEM_USER.email

    def matching_permissions(self) -> list[DocPermission]:
        """Permission rows whose role applies to this user (own roles, or "All").

        Returns an empty list when :attr:`is_unrestricted` — callers must
        check that first and treat it as "everything allowed", not "nothing
        matched". A DocType with no permission rows at all is closed to
        everyone else — "no permissions defined" means nobody has been
        granted access yet, not "open to anyone logged in". A doctype that
        should genuinely be world-readable needs an explicit
        `{"role": "All", ...}` permission row.
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
