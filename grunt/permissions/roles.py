"""Bare role-name check - no DocType involved.

Distinct from ``permission_checker``/``RoleAccess`` (``rbac.py``/``access.py``),
which are always doctype+action shaped. This is the primitive behind
``@grunt.whitelist(roles=[...])`` for RPC-style methods that aren't CRUD on a
single doctype.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


def user_has_roles(user: User | None, roles: list[str]) -> bool:
    """True if ``user`` holds at least one of ``roles``."""
    if user is None:
        return False
    user_roles = getattr(user, "roles", None) or []
    return any(r in user_roles for r in roles)
