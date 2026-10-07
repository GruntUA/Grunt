"""Permission API mixin for GruntApp facade."""

from __future__ import annotations

from typing import Any

import grunt
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
        dt = await grunt.get_meta(doctype)
        if dt is None:
            return False
        user = grunt.get_user()
        doc: dict[str, Any] | None = None
        if doc_id:
            doc = await grunt.db.get_value(doctype, doc_id, "*")
        return await permission_checker.check(
            user,
            dt.doc,
            action,
            doc,
        )
