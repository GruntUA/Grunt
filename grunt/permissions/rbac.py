"""Role-based access control."""

from grunt.errors import forbidden
from grunt.i18n import NP_, _, pgettext
from grunt.permissions import shares
from grunt.permissions.access import RoleAccess
from grunt.permissions.child import child_allowed, is_child
from grunt.permissions.types import PermissionAction
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.doctype import DocType
lazy from grunt.permissions.query import grants, row_allowed

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

        With *doc* the answer is the row predicate of *action* evaluated against
        it (:func:`grunt.permissions.query.row_allowed`) - the very expression a
        list query filters by, so a document opens exactly when a list would
        hold it.

        ``doc=None`` is the DocType-level pre-flight: may the user perform
        *action* on *some* row - a role grants it (whatever its ``match``), a
        parent of a child DocType is readable, or a document is shared. Rows are
        then narrowed by the predicate.
        """
        access = RoleAccess(doctype, user)
        if access.is_unrestricted:
            return True
        if doc is not None:
            meta = doctype if isinstance(doctype, Meta) else Meta(doctype)
            return await row_allowed(user, meta, action, doc)
        if is_child(doctype):
            return await child_allowed(user, doctype, action)
        if any(grants(perm, action) for perm in access.matching_permissions()):
            return True
        if action not in shares.SHAREABLE_ACTIONS or getattr(doctype, "is_singleton", False):
            return False
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
