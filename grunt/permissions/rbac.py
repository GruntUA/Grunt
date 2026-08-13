"""Role-based access control."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from grunt.errors import forbidden
from grunt.permissions.types import PermissionAction

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType

logger = structlog.get_logger()

# _PERM_CACHE key: (user_email, frozenset(roles), doctype_name, id(permissions_list), action)
# _HIDDEN_CACHE key: (user_email, frozenset(roles), doctype_name, id(permissions_list))
# id(permissions_list) distinguishes different DocType objects sharing the same name.
# Only populated for the doc=None path (list/count operations).
# Invalidated per-doctype via invalidate_permission_cache().
_PERM_CACHE: dict[tuple, bool] = {}
_HIDDEN_CACHE: dict[tuple, frozenset] = {}


def invalidate_permission_cache(doctype_name: str | None = None) -> None:
    """Evict cached permission results for a given DocType, or all if None."""
    for cache in (_PERM_CACHE, _HIDDEN_CACHE):
        if doctype_name is None:
            cache.clear()
        else:
            stale = [k for k in cache if k[2] == doctype_name]
            for k in stale:
                cache.pop(k, None)


class PermissionChecker:
    async def check(
        self,
        user: User,
        doctype: DocType,
        action: PermissionAction,
        doc: dict | None = None,
    ) -> bool:
        if getattr(user, "is_superadmin", False):
            return True

        if not doctype.permissions:
            return True  # No permissions defined = open (dev mode)

        user_roles = frozenset(getattr(user, "roles", []) or [])

        # Cache only when doc is None (list/count); match-expression checks are doc-specific.
        # Include id(doctype.permissions) so that different DocType objects with the same
        # name but different permission lists (common in tests) get separate cache entries.
        cache_key: tuple | None = None
        if doc is None:
            cache_key = (user.email, user_roles, doctype.name, id(doctype.permissions), action)
            cached = _PERM_CACHE.get(cache_key)
            if cached is not None:
                return cached

        result = False
        for perm in doctype.permissions:
            role = perm.role if hasattr(perm, "role") else ""
            if role not in user_roles and role != "All":
                continue
            perm_val = getattr(perm, action, False)
            if not perm_val:
                continue
            # Check match expression
            match_expr = perm.match if hasattr(perm, "match") else None
            if match_expr and doc and not self._eval_match(match_expr, user, doc, doctype.name):
                continue
            result = True
            break

        if cache_key is not None:
            _PERM_CACHE[cache_key] = result
        return result

    async def require(
        self,
        user: User,
        doctype: DocType,
        action: PermissionAction,
        doc: dict | None = None,
    ) -> None:
        allowed = await self.check(user, doctype, action, doc)
        if not allowed:
            raise forbidden()

    def hidden_fields(
        self,
        user: User,
        doctype: DocType,
    ) -> frozenset[str]:
        """Return the set of field names the user is NOT allowed to see.

        If the user is superadmin or no permissions are defined, returns empty set.
        For each matching role permission, the union of hidden_fields from the
        *most permissive* (first matching) rule is used — i.e., if any matching
        rule exposes a field, it is visible.
        """
        if getattr(user, "is_superadmin", False):
            return frozenset()
        if not doctype.permissions:
            return frozenset()

        user_roles = frozenset(getattr(user, "roles", []) or [])

        # id(doctype.permissions) distinguishes DocType objects with the same name
        # but different permission lists (see check() for the same pattern).
        cache_key = (user.email, user_roles, doctype.name, id(doctype.permissions))
        cached_hidden = _HIDDEN_CACHE.get(cache_key)
        if cached_hidden is not None:
            return cached_hidden

        hidden: set[str] = set()
        matched = False

        for perm in doctype.permissions:
            role = perm.role if hasattr(perm, "role") else ""
            if role not in user_roles and role != "All":
                continue
            read_ok = getattr(perm, "read", False)
            if not read_ok:
                continue
            perm_hidden = getattr(perm, "hidden_fields", [])
            if not matched:
                hidden = set(perm_hidden)
                matched = True
            else:
                # Intersect: a field is hidden only if ALL matching rules hide it
                hidden &= set(perm_hidden)

        result = frozenset(hidden)
        _HIDDEN_CACHE[cache_key] = result
        return result

    def _eval_match(self, match_expr: str, user: User, doc: dict, doctype_name: str = "") -> bool:
        try:
            from simpleeval import simple_eval

            names = {
                "user": user.email,
                "owner": doc.get("owner"),
                "doc": doc,
            }
            return bool(simple_eval(match_expr, names=names))
        except Exception:
            # Fail CLOSED: an unevaluable match expression (typo, unsupported
            # syntax, ...) must deny the row, not silently grant it — the
            # opposite default would turn a broken permission rule into an
            # open one. Logged so a misconfigured rule is visible to admins.
            logger.warning(
                "rbac.match_eval_error", doctype=doctype_name, match=match_expr
            )
            return False


permission_checker = PermissionChecker()
