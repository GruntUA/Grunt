"""Permission API mixin for GruntApp facade."""

from typing import Any

from grunt.db.api import GruntDB
from grunt.local import user_email
from grunt.metadata.registry import doctype_registry
from grunt.permissions.perms import has_perm as _has_perm
from grunt.permissions.rbac import permission_checker
from grunt.permissions.types import PermissionAction


class PermissionAPI:
    """Permission and identity helper methods for GruntApp."""

    async def has_permission(
        self,
        doctype: str,
        action: PermissionAction,
        doc_id: str | None = None,
    ) -> bool:
        """Check whether the current user has the given permission.

        ``action`` is one of ``"read"``, ``"select"``, ``"write"``, ``"create"``,
        ``"delete"``::

            if not await grunt.has_permission("Invoice", "delete"):
                grunt.throw("You cannot delete invoices")
        """
        dt = await doctype_registry.get_meta(doctype)
        if dt is None:
            return False
        user_email()  # 401 without a user, as before
        doc: dict[str, Any] | None = None
        if doc_id:
            doc = await GruntDB().get_value(doctype, doc_id, "*")
        return await permission_checker.check(dt.doc, action, doc)

    async def has_perm(self, perm: str, *, user: str | None = None) -> bool:
        """Whether the current user (or *user*, an email) holds permission *perm*
        through their roles - a capability, not a document right::

            if not await grunt.has_perm("grunt.moderate_comments"):
                grunt.throw("You cannot edit other people's comments")

        Declare an app's permissions in ``hooks.py`` (``permissions = [...]``).
        """
        return await _has_perm(perm, user=user)
