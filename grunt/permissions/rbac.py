"""Role-based access control."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.errors import forbidden
from grunt.permissions.access import RoleAccess
from grunt.permissions.match import PermissionMatch
from grunt.permissions.types import PermissionAction

# Human-readable action names for the "insufficient permissions" message, so a
# toast says *which* DocType and *which* operation was denied instead of a bare
# "Недостатньо прав".
_ACTION_UK: dict[str, str] = {
    "read": "читання",
    "select": "вибір у полі",
    "write": "редагування",
    "create": "створення",
    "delete": "видалення",
    "submit": "проведення",
    "cancel": "скасування",
    "report": "звіти",
}

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.document.meta import Meta
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
        doctype: DocType | Meta,
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
                return cached or await self._shared(user, doctype, action, doc)

        result = False
        for perm in access.matching_permissions():
            perm_val = getattr(perm, action, False)
            # "read" implies "select" — a role that can read the whole
            # document can certainly resolve its identifier for a picker.
            if not perm_val and action == "select":
                perm_val = getattr(perm, "read", False)
            if not perm_val:
                continue
            # Check match expression
            match_expr = perm.match if hasattr(perm, "match") else None
            if match_expr and doc:
                matched = await PermissionMatch(match_expr).evaluate_doc(doc, user, doctype)
                if not matched:
                    continue
            result = True
            break

        # Row-level User Permissions narrow the role grant for a specific doc.
        # (doc=None list/count checks are filtered in apply_permission_filter.)
        if result and doc is not None:
            from grunt.permissions.user_permissions import doc_passes

            if not await doc_passes(user, doctype, doc):
                result = False

        # Comments / tags / attachments: readable only with the referenced doc.
        if result and doc is not None and action in ("read", "select"):
            from grunt.permissions.reference import reference_readable

            result = await reference_readable(user, doctype, doc)

        if cache_key is not None:
            _PERM_CACHE[cache_key] = result
        return result or await self._shared(user, doctype, action, doc)

    @staticmethod
    async def _shared(
        user: User, doctype: DocType | Meta, action: PermissionAction, doc: dict | None
    ) -> bool:
        """Fallback when roles deny: a ``SharedWith`` grant (never cached — shares
        change without touching the role cache). With ``doc`` only a share of
        that very document counts; without it, a share of any document of the
        DocType lets the doctype-level pre-flight pass so the per-document
        check can decide."""
        from grunt.permissions.shares import SHAREABLE_ACTIONS, has_share

        if action not in SHAREABLE_ACTIONS or getattr(doctype, "is_singleton", False):
            return False
        if doc is not None:
            if not doc.get("name"):
                return False
            return await has_share(user, doctype.name, action, doc["name"])
        return await has_share(user, doctype.name, action)

    async def require(
        self,
        user: User,
        doctype: DocType | Meta,
        action: PermissionAction,
        doc: dict | None = None,
    ) -> None:
        allowed = await self.check(user, doctype, action, doc)
        if not allowed:
            label = getattr(doctype, "label", None) or getattr(doctype, "name", "")
            verb = _ACTION_UK.get(action, action)
            raise forbidden(f"Немає доступу: {verb} «{label}»")

    def hidden_fields(
        self,
        user: User,
        doctype: DocType | Meta,
    ) -> frozenset[str]:
        """Return the set of field names the user is NOT allowed to see.

        If no permissions are defined, returns empty set. For each matching
        role permission, the union of hidden_fields from the *most permissive*
        (first matching) rule is used — i.e., if any matching rule exposes a
        field, it is visible.
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
