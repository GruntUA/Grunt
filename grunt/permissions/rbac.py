"""Role-based access control."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.errors import forbidden
from grunt.permissions.access import RoleAccess
from grunt.permissions.match import PermissionMatch
from grunt.permissions.types import PermissionAction

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType

# _PERM_CACHE key: (user_email, frozenset(roles), doctype_name, id(permissions_list), action)
# _HIDDEN_CACHE key: (user_email, frozenset(roles), doctype_name, id(permissions_list))
# id(permissions_list) distinguishes different DocType objects sharing the same name.
# Only populated for the doc=None path (list/count operations).
# Invalidated per-doctype via invalidate_permission_cache().
#
# Unbounded, no TTL: entries accumulate for the process lifetime — bounded in
# practice by (distinct users x distinct role-sets x DocTypes x actions),
# which for a typical deployment (roles come from a small fixed Role table,
# not per-request) stays small relative to available memory. If that stops
# holding (e.g. per-request synthetic roles), this needs a real eviction
# policy, not just invalidate_permission_cache().
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
        """Check whether *user* may perform *action* on *doctype* (optionally *doc*).

        ``doc=None`` has two effects, not one: it means "no specific document to
        check" (so any ``match`` expression on a matching permission row is
        skipped — a list/count-style check), *and* it makes the result eligible
        for the per-(user, doctype, action) cache below, since without a doc
        there's nothing document-specific that could make the answer vary.
        Passing a ``doc`` disables caching for that call (match evaluation is
        necessarily per-document) — there's no separate flag for this, the two
        behaviors are intentionally tied to the same argument.
        """
        access = RoleAccess(doctype, user)
        if access.is_unrestricted:
            return True

        # Cache only when doc is None (list/count); match-expression checks are doc-specific.
        # Include id(doctype.permissions) so that different DocType objects with the same
        # name but different permission lists (common in tests) get separate cache entries.
        cache_key: tuple | None = None
        if doc is None:
            cache_key = (
                user.email,
                access.user_roles,
                doctype.name,
                id(doctype.permissions),
                action,
            )
            cached = _PERM_CACHE.get(cache_key)
            if cached is not None:
                return cached

        result = False
        for perm in access.matching_permissions():
            perm_val = getattr(perm, action, False)
            if not perm_val:
                continue
            # Check match expression
            match_expr = perm.match if hasattr(perm, "match") else None
            if match_expr and doc:
                matched = PermissionMatch(match_expr).evaluate(
                    doc, user, doctype_name=doctype.name
                )
                if not matched:
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
        access = RoleAccess(doctype, user)
        if access.is_unrestricted:
            return frozenset()

        # id(doctype.permissions) distinguishes DocType objects with the same name
        # but different permission lists (see check() for the same pattern).
        cache_key = (user.email, access.user_roles, doctype.name, id(doctype.permissions))
        cached_hidden = _HIDDEN_CACHE.get(cache_key)
        if cached_hidden is not None:
            return cached_hidden

        hidden: set[str] = set()
        matched = False

        for perm in access.matching_permissions():
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


permission_checker = PermissionChecker()
