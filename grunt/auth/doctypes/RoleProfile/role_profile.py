"""RoleProfile - a set of roles handed out together (``User.role_profiles``).

A user's ``UserRole`` rows are of two kinds: assigned by hand, and copied from
their profiles (``role_profile`` set). On every save of the user the copied
rows are rebuilt from the profiles - see :func:`with_profile_roles`; saving a
profile rebuilds them for each of its users.
"""

from collections.abc import Sequence
from typing import Any

from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session

#: A role assignment's identity: the same role in the same scope.
_KEY_FIELDS = ("role_name", "scope_doctype", "scope_value")


def _key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(f) or "") for f in _KEY_FIELDS)


class RoleProfile(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    profile_name: str  # Name
    description: str | None = None  # Description
    roles: list[dict] = []  # Table: RoleProfileRole

    # end: auto-generated types

    async def validate(self) -> None:
        seen: set[tuple[str, ...]] = set()
        rows: list[dict[str, Any]] = []
        for row in self.roles or []:
            if not isinstance(row, dict) or not row.get("role_name"):
                continue
            if bool(row.get("scope_doctype")) != bool(row.get("scope_value")):
                throw(
                    _("Role “%(role)s”: a scope needs both the document type and the document")
                    % {"role": _(row["role_name"])},
                    "VALIDATION_ERROR",
                )
            if _key(row) not in seen:  # the same role twice adds nothing
                seen.add(_key(row))
                rows.append(row)
        self.roles = rows

    async def after_save(self) -> None:
        if self.name:
            await resync_users(self.name)

    async def before_delete(self) -> None:
        users = await profile_users(self.name) if self.name else []
        if users:
            throw(
                _("The role profile is assigned to %(n)s users - take it away from them first")
                % {"n": len(users)},
                "VALIDATION_ERROR",
            )


async def profile_users(profile: str) -> list[str]:
    """Names of the users holding *profile*."""
    rows = await _db.get_all(
        "UserRoleProfile",
        filters={"role_profile": profile, "parent_doctype": "User"},
        pluck="parent_name",
        limit=None,
    )
    return sorted(set(rows))


async def resync_users(profile: str) -> None:
    """Rebuild the profile's roles for every user holding it."""
    for user in await profile_users(profile):
        held = await _db.get_all(
            "UserRoleProfile",
            filters={"parent_name": user, "parent_doctype": "User"},
            pluck="role_profile",
            limit=None,
            order_by="idx",
            order="asc",
        )
        await documents.save_doc(
            "User",
            user,
            {"role_profiles": [{"role_profile": p} for p in held]},
            ignore_permissions=True,
        )


async def with_profile_roles(
    roles: Sequence[dict[str, Any]], profiles: list[str]
) -> list[dict[str, Any]]:
    """The user's role rows: those assigned by hand (no ``role_profile``) and
    then the roles of *profiles*, in order - a role the user already holds by
    hand in the same scope, without a period, isn't added again. One held for
    a period (``valid_from``/``valid_to``) is: the profile's grant stays when
    the period is over."""
    manual = [r for r in roles if isinstance(r, dict) and not r.get("role_profile")]
    held = {_key(r) for r in manual if not r.get("valid_from") and not r.get("valid_to")}
    out = list(manual)
    if not profiles:
        return out
    rows = await _db.get_all(
        "RoleProfileRole",
        filters={"parent_name__in": profiles, "parent_doctype": "RoleProfile"},
        fields=["parent_name", *_KEY_FIELDS],
        limit=None,
        order_by="idx",
        order="asc",
    )
    for profile in profiles:
        for row in rows:
            if row.parent_name != profile or _key(row) in held:
                continue
            held.add(_key(row))
            out.append(
                {
                    "role_name": row.role_name,
                    "scope_doctype": row.scope_doctype or None,
                    "scope_value": row.scope_value or None,
                    "role_profile": profile,
                }
            )
    return out
