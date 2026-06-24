"""Permission API mixin for GruntApp facade.

Identity/guard logic lives in :mod:`grunt.context` (context accessors) and
:mod:`grunt.permissions.guards` (permission guards) as module-level functions —
import and call those directly. ``_require_user`` stays as a thin facade wrapper
because external code still calls ``grunt._require_user()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.context import require_user
from grunt.metadata.registry import doctype_registry
from grunt.permissions.types import PermissionAction

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


class PermissionAPI:
    """Permission and identity helper methods for GruntApp."""

    def _require_user(self) -> User:
        return require_user()

    async def has_permission(
        self,
        doctype: str,
        action: PermissionAction,
        doc_id: str | None = None,
    ) -> bool:
        """Check whether the current user has the given permission.

        ``action`` is one of ``"read"``, ``"write"``, ``"create"``, ``"delete"``,
        ``"submit"``::

            if not await grunt.has_permission("Invoice", "delete"):
                grunt.throw("You cannot delete invoices")
        """
        from grunt.app import grunt
        from grunt.permissions.rbac import permission_checker

        dt = await doctype_registry.get(doctype)
        user = require_user()
        doc: dict[str, Any] | None = None
        if doc_id:
            doc = await grunt.db.get_value(doctype, doc_id, "*")
        return await permission_checker.check(
            user,
            dt,
            action,
            doc,
        )
