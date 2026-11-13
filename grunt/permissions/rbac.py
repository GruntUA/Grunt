"""Role-based access control."""

from grunt.document.meta import Meta
from grunt.errors import forbidden
from grunt.i18n import NP_, _, pgettext
from grunt.local import session_user
from grunt.metadata.doctype import DocType
from grunt.permissions import query
from grunt.permissions.roles import role_access
from grunt.permissions.types import PermissionAction, WriteAction

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
    "export": NP_("permission", "export"),
    "import": NP_("permission", "import"),
    "print": NP_("permission", "print"),
    "share": NP_("permission", "share"),
}


class PermissionChecker:
    async def check(
        self,
        doctype: DocType | Meta,
        action: PermissionAction,
        doc: dict | None = None,
        *,
        user: str | None = None,
    ) -> bool:
        """Check whether *user* (an email; ``None`` - the user the context runs as)
        may perform *action* on *doctype* (optionally *doc*) - see
        :func:`grunt.permissions.query.allowed`."""
        return await query.allowed(doctype, action, doc, user=user)

    async def require(
        self,
        doctype: DocType | Meta,
        action: PermissionAction,
        doc: dict | None = None,
        *,
        user: str | None = None,
    ) -> None:
        """:meth:`check`, raising 403 when it says no."""
        allowed = await self.check(doctype, action, doc, user=user)
        if not allowed:
            label = getattr(doctype, "label", None) or getattr(doctype, "name", "")
            verb = _ACTION_VERBS.get(action, action)
            raise forbidden(
                _("No access: %(action)s “%(doctype)s”")
                % {"action": pgettext("permission", verb), "doctype": _(label)}
            )

    async def require_in_scope(
        self,
        doctype: DocType | Meta,
        action: WriteAction,
        row: dict,
        *,
        user: str | None = None,
    ) -> None:
        """403 when *row* - the document as it is about to be stored - lies
        outside what *action* (``create`` / ``write``) grants *user*: the rule's
        ``match``, shares and User Permissions are evaluated against the new
        values, not only the stored ones, so a change can't carry a document
        out of the user's scope (or create it outside)."""
        if await self.check(doctype, action, row, user=user):
            return
        if action == "create":
            detail = _("No access: you may not create a document with these values")
        else:
            detail = _("No access: after this change the document would be outside your access")
        raise forbidden(detail)

    async def can_share(
        self,
        doctype: DocType | Meta,
        doc: dict | None = None,
        *,
        user: str | None = None,
    ) -> bool:
        """``share`` - and ``write``: sharing must not hand out (a link to, or a
        Write share of) a document beyond what the sharer may do with it."""
        return await self.check(doctype, "share", doc, user=user) and await self.check(
            doctype, "write", doc, user=user
        )

    async def require_share(
        self,
        doctype: DocType | Meta,
        doc: dict | None = None,
        *,
        user: str | None = None,
    ) -> None:
        """:meth:`can_share`, raising 403 when it says no."""
        await self.require(doctype, "share", doc, user=user)
        await self.require(doctype, "write", doc, user=user)

    async def readonly_fields(
        self,
        doctype: DocType | Meta,
        *,
        user: str | None = None,
    ) -> frozenset[str]:
        """The field names *user* (``None`` - the context's) sees but may not
        change on *doctype* (see :attr:`RoleAccess.readonly_fields`)."""
        return (await role_access(doctype, user or session_user())).readonly_fields

    async def hidden_fields(
        self,
        doctype: DocType | Meta,
        *,
        user: str | None = None,
    ) -> frozenset[str]:
        """The field names *user* (``None`` - the context's) may not see on
        *doctype* (see :attr:`RoleAccess.hidden_fields`)."""
        return (await role_access(doctype, user or session_user())).hidden_fields


permission_checker = PermissionChecker()
