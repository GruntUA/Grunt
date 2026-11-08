"""Role-based access control."""

from grunt.errors import forbidden
from grunt.i18n import NP_, _, pgettext
from grunt.permissions import shares
from grunt.permissions.access import RoleAccess
from grunt.permissions.child import child_allowed, is_child
from grunt.permissions.match import PermissionMatch
from grunt.permissions.types import PermissionAction
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.doctype import DocType
lazy from grunt.permissions.reference import reference_readable, reference_sources
lazy from grunt.permissions.user_permissions import doc_passes

# Human-readable action names for the "insufficient permissions" message, so a
# toast says *which* DocType and *which* operation was denied instead of a bare
# "Недостатньо прав".
_ACTION_VERBS: dict[str, str] = {
    "read": NP_("permission", "read"),
    "select": NP_("permission", "select in a field"),
    "write": NP_("permission", "write"),
    "create": NP_("permission", "create"),
    "delete": NP_("permission", "delete"),
    "report": NP_("permission", "reports"),
}


class PermissionChecker:
    async def check(
        self,
        user: User,
        doctype: DocType | Meta,
        action: PermissionAction,
        doc: dict | None = None,
    ) -> bool:
        """Check whether *user* may perform *action* on *doctype* (optionally *doc*).

        ``doc=None`` means "no specific document": a ``match`` expression on a
        matching permission row is skipped (a list/count-style check - rows are
        narrowed by ``read_predicate`` instead).

        Nothing is cached: without a doc the check is one pass over the user's
        permission rows, and no key is cheaper than those rows themselves.
        """
        access = RoleAccess(doctype, user)
        if access.is_unrestricted:
            return True

        if is_child(doctype):
            return await child_allowed(user, doctype, action, doc)

        # Comments / tags / attachments / files in a folder: a row that points
        # at a document is readable exactly when that document is - the
        # role's `match` only governs rows that point at nothing.
        inherited: bool | None = None
        if doc is not None and action in ("read", "select") and reference_sources(doctype):
            inherited = await reference_readable(user, doctype, doc)

        result = False
        for perm in access.matching_permissions():
            perm_val = getattr(perm, action, False)
            # "read" implies "select" - a role that can read the whole
            # document can certainly resolve its identifier for a picker.
            if not perm_val and action == "select":
                perm_val = getattr(perm, "read", False)
            if not perm_val:
                continue
            # Check match expression
            match_expr = perm.match if hasattr(perm, "match") else None
            if match_expr and doc and inherited is None:
                matched = await PermissionMatch(match_expr).evaluate_doc(doc, user, doctype)
                if not matched:
                    continue
            result = True
            break

        # Row-level User Permissions narrow the role grant for a specific doc.
        # (doc=None list/count checks are filtered by read_predicate.)
        if result and doc is not None and not await doc_passes(user, doctype, doc):
            result = False

        if inherited is False:
            result = False

        return result or await self._shared(user, doctype, action, doc)

    @staticmethod
    async def _shared(
        user: User, doctype: DocType | Meta, action: PermissionAction, doc: dict | None
    ) -> bool:
        """Fallback when roles deny: a ``SharedWith`` grant. With ``doc`` only a share of
        that very document counts; without it, a share of any document of the
        DocType lets the doctype-level pre-flight pass so the per-document
        check can decide."""
        if action not in shares.SHAREABLE_ACTIONS or getattr(doctype, "is_singleton", False):
            return False
        if doc is not None:
            if not doc.get("name"):
                return False
            return await shares.has_share(user, doctype.name, action, doc["name"])
        return await shares.has_share(user, doctype.name, action)

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
            verb = _ACTION_VERBS.get(action, action)
            raise forbidden(
                _("No access: %(action)s “%(doctype)s”")
                % {"action": pgettext("permission", verb), "doctype": _(label)}
            )

    def hidden_fields(
        self,
        user: User,
        doctype: DocType | Meta,
    ) -> frozenset[str]:
        """Return the set of field names the user is NOT allowed to see.

        If no permissions are defined, returns empty set. For each matching
        role permission, the union of hidden_fields from the *most permissive*
        (first matching) rule is used - i.e., if any matching rule exposes a
        field, it is visible.
        """
        access = RoleAccess(doctype, user)
        if access.is_unrestricted:
            return frozenset()

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

        return frozenset(hidden)


permission_checker = PermissionChecker()
