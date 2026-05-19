"""Permission API mixin for GruntApp facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.user import User


class PermissionAPI:
    """Permission and identity helper methods for GruntApp."""

    def _require_user(self) -> User:
        from grunt.context import _user_ctx  # noqa: PLC0415

        u = _user_ctx.get()
        if u is None:
            raise RuntimeError("grunt: no active user.")
        return u

    @staticmethod
    def _apply_hidden_fields_to_doc(
        doc: dict[str, Any],
        hidden_fields: frozenset[str],
    ) -> dict[str, Any]:
        if not hidden_fields:
            return doc
        for field in hidden_fields:
            doc.pop(field, None)
        return doc

    @staticmethod
    def _apply_hidden_fields_to_rows(
        rows: list[dict[str, Any]],
        hidden_fields: frozenset[str],
    ) -> list[dict[str, Any]]:
        if not hidden_fields:
            return rows
        for row in rows:
            for field in hidden_fields:
                row.pop(field, None)
        return rows

    async def _read_guard(self, doctype: str) -> tuple[Any, User, frozenset[str]]:
        """Shared pre-flight for every read operation at the high-level layer.

        Returns ``(dt, user, hidden_fields)``.  Raises ``403`` when the user
        has no *read* permission on the DocType.
        """
        from grunt.permissions.rbac import permission_checker  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        user = self._require_user()
        await permission_checker.require(user, dt, "read")
        hidden_fields = permission_checker.hidden_fields(user, dt)
        return dt, user, hidden_fields

    async def _write_guard(self, doctype: str, action: str) -> tuple[Any, User, AsyncSession]:
        """Shared pre-flight for every write operation at the high-level layer.

        Returns ``(dt, user, session)``.  Raises ``403`` when the user has no
        permission for *action* (``"create"``, ``"write"``, or ``"delete"``).
        """
        from grunt.permissions.rbac import permission_checker  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        user = self._require_user()
        await permission_checker.require(user, dt, action)
        return dt, user, self._require_session()  # type: ignore[attr-defined]

    async def has_permission(
        self,
        doctype: str,
        action: str,
        doc_id: str | None = None,
    ) -> bool:
        """Check whether the current user has the given permission.

        ``action`` is one of ``"read"``, ``"write"``, ``"create"``, ``"delete"``,
        ``"submit"``::

            if not await grunt.has_permission("Invoice", "delete"):
                grunt.throw("You cannot delete invoices")
        """
        from grunt.permissions.rbac import permission_checker  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        user = self._require_user()
        doc: dict[str, Any] | None = None
        if doc_id:
            doc = await self.db.get_value(doctype, doc_id, "*")  # type: ignore[attr-defined]
        return await permission_checker.check(
            user,
            dt,
            action,
            doc,  # type: ignore[arg-type]
        )
