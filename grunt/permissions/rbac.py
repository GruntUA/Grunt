"""Role-based access control."""

from grunt.errors import forbidden
from grunt.i18n import NP_, _, pgettext
from grunt.permissions import query, shares
from grunt.permissions.access import RoleAccess
from grunt.permissions.child import child_allowed, is_child
from grunt.permissions.types import PermissionAction
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.doctype import DocType

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
        it (``query.row_allowed``) - the very expression a
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
            return await query.row_allowed(user, meta, action, doc)
        if is_child(doctype):
            return await child_allowed(user, doctype, action)
        if any(perm.grants(action) for perm in access.matching_permissions()):
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
        """The field names *user* may not see on *doctype* (see
        :attr:`RoleAccess.hidden_fields`)."""
        return RoleAccess(doctype, user).hidden_fields


permission_checker = PermissionChecker()
