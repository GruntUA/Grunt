"""Role-based access facts for a (doctype, user) pair.

`PermissionChecker.check()`/`.hidden_fields()` (rbac.py) and
`read_predicate()` (query.py) each independently re-derived the same
thing: which `DocPermission` rows a user's roles actually match. Wrapping
that here means the three call sites can't drift the way `PermissionMatch`'s
two evaluation modes already had.

No role, including "System Manager", bypasses permission rows outright -
access is always decided by matching rows. Most DocTypes grant System
Manager unrestricted CRUD via an explicit `{"role": "System Manager", ...}`
row, but a few (read-only logs, audit trails) deliberately don't grant
write/create/delete to anyone, System Manager included - a blanket
role-based bypass would silently defeat that.

The one exception is the internal SYSTEM_USER identity (`grunt.system_context()`
- background tasks, hooks, migrations): it bypasses permission rows entirely,
same as before. That's an unrelated, non-human concern from "how do people
get admin rights" - it's what lets the framework itself write to doctypes
(like ErrorLog) that intentionally grant no write access to any real role.

The module depends on nothing above it: the user is their email and roles
(looked up by :func:`grunt.permissions.roles.role_access`), the DocType is
described by what it reads of it (:class:`Target`), so every layer can ask it
without an import cycle.
"""

from collections.abc import Collection, Sequence
from typing import Any, Protocol

from grunt.auth.constants import SYSTEM_USER_EMAIL
from grunt.metadata.permission import DocPermission


class Target(Protocol):
    """What is asked about - a ``DocType`` model or its ``Meta``."""

    @property
    def name(self) -> str:
        """The DocType name."""
        raise NotImplementedError

    @property
    def permissions(self) -> Sequence[DocPermission]:
        """The DocType's permission rows."""
        raise NotImplementedError

    @property
    def fields(self) -> Sequence[Any]:
        """The DocType's fields (``fieldname``, ``default``)."""
        raise NotImplementedError


class RoleAccess:
    """Role-based access facts for *user* (an email) holding *roles* on *doctype*,
    computed once. :func:`grunt.permissions.roles.role_access` looks the roles up."""

    def __init__(self, doctype: Target, user: str | None, roles: Collection[str]) -> None:
        self.doctype = doctype
        self.user = user
        self.user_roles: frozenset[str] = frozenset(roles)

    @property
    def has_unrestricted_read(self) -> bool:
        """True when a matching permission grants ``read`` with no row ``match`` -
        the user may read every row, not just a filtered subset.

        ``read_predicate()`` and the Link/tree picker gates both need to
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
    def hidden_fields(self) -> frozenset[str]:
        """Field names the user may not see - nor write, filter, sort, group or
        search by. A field is hidden only when *every* matching rule that grants
        ``read`` hides it: any rule exposing it makes it visible. Empty when no
        rule grants ``read`` (the read guard refuses then anyway)."""
        if self.is_unrestricted:
            return frozenset()
        hidden: set[str] | None = None
        for perm in self.matching_permissions():
            if not getattr(perm, "read", False):
                continue
            rule = set(getattr(perm, "hidden_fields", None) or [])
            hidden = rule if hidden is None else hidden & rule
        return frozenset(hidden or ())

    def hidden_changes(self, data: dict, existing: dict | None = None) -> set[str]:
        """Hidden fields that writing *data* would change - over *existing*, or on
        a new document past the field's default (a form may send defaults back).
        The user can't set what they can't see."""
        hidden = self.hidden_fields
        changed: set[str] = set()
        for field in hidden & data.keys():
            value = data[field]
            if existing is not None:
                if value != existing.get(field):
                    changed.add(field)
                continue
            if value in (None, "", []):
                continue
            meta_field = next((f for f in self.doctype.fields if f.fieldname == field), None)
            default = getattr(meta_field, "default", None)
            if default is None or str(value) != str(default):
                changed.add(field)
        return changed

    @property
    def is_unrestricted(self) -> bool:
        """True only for the internal SYSTEM_USER identity - never for a human
        role, System Manager included (see module docstring)."""

        return self.user == SYSTEM_USER_EMAIL

    def matching_permissions(self) -> list[DocPermission]:
        """Permission rows whose role applies to this user (own roles, or "All").

        Returns an empty list when :attr:`is_unrestricted` - callers must
        check that first and treat it as "everything allowed", not "nothing
        matched". A DocType with no permission rows at all is closed to
        everyone else - "no permissions defined" means nobody has been
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
