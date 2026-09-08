"""Ґрунт — Python Framework for Building CMS, ERP, and Business Apps.

Primary imports for app developers:
    from grunt import db, msgprint, throw, notify

Example usage in a DocType controller:
    from grunt import db, msgprint, get_current_user
    from grunt.app import grunt

    class Invoice:
        async def before_save(self):
            # Get related document
            order = await grunt.get_doc("Order", self.doc.order_id)

            # Check business rule
            if await db.exists("Lock", self.doc.id):
                throw("This invoice is locked")

            # Check permissions
            current_user = await get_current_user()
            if not await grunt.has_permission("Contract", "write", self.doc.contract_id):
                throw("Read-only access")

            # Notify user
            msgprint(f"Amount: {self.doc.total}", type="success")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from contextlib import AbstractAsyncContextManager
    from typing import Any, NoReturn, TypeVar

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.app import GruntDB
    from grunt.auth.doctypes.User.user import User
    from grunt.document.base import Document

    _T = TypeVar("_T")
    _F = TypeVar("_F", bound=Callable)

    db: GruntDB

    # ── Decorators / utilities ────────────────────────────────────────────────
    def whitelist(
        allow_guest: bool = False,
        *,
        roles: list[str] | None = None,
        require: Callable[[User], bool | Awaitable[bool]] | None = None,
    ) -> Callable[[_F], _F]: ...
    def throw(message: str, code: str = "ERROR", title: str = "") -> NoReturn: ...
    async def get_current_user() -> User: ...
    def get_engine() -> AsyncEngine: ...
    async def log_error(
        *,
        exc: BaseException | None = None,
        title: str | None = None,
        message: str | None = None,
        context: str = "Manual",
        method: str | None = None,
        user: str | None = None,
        app: str | None = None,
        http_status: int | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        request_id: str | None = None,
        reference_doctype: str | None = None,
        reference_name: str | None = None,
        session: AsyncSession | None = None,
    ) -> str | None:
        """Persist an error to the ``ErrorLog`` DocType. Best-effort; never raises."""
        ...

    # ── Document API ──────────────────────────────────────────────────────────
    # Not `@overload` (this stub is never executed — see __getattr__ below — and
    # `@overload` outside a .pyi file requires a real dispatching implementation).
    # Pass a doctype name for a dict result, or a Document subclass for a typed
    # controller instance — see the real overloads on GruntApp.get_doc.
    async def get_doc[D: Document](
        doctype: str | type[D],
        id_or_name: str | None = None,
        *,
        expand: list[str] | None = None,
    ) -> dict[str, Any] | D: ...
    async def find_doc[D: Document](
        doctype: str | type[D],
        id_or_name: str | None = None,
        *,
        expand: list[str] | None = None,
    ) -> dict[str, Any] | D | None: ...
    async def get_doc_instance(doctype: str, id_or_name: str) -> Document:
        """Registry-based fetch for when the doctype is only known at runtime
        (e.g. a workflow/task operating on a caller-supplied doctype name) —
        prefer `get_doc(SomeClass, id)` when the class is known statically."""
        ...
    async def new_doc(
        doctype: str,
        data: dict[str, Any],
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]: ...
    async def save_doc(
        doctype: str,
        id_or_name: str,
        data: dict[str, Any],
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]: ...
    async def delete_doc(
        doctype: str, id_or_name: str, replace_with: str | None = None
    ) -> None: ...
    async def rename_doc(doctype: str, old_id: str, new_id: str) -> dict[str, Any]: ...
    async def get_list(
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        page: int = 1,
        order_by: str = "modified_at",
        order: str = "desc",
        search: str | None = None,
    ) -> list[dict[str, Any]]: ...
    async def count(
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> int: ...
    async def exists(
        doctype: str,
        filters: dict[str, Any] | str,
    ) -> str | None: ...
    async def get_value(doctype: str, id_or_name: str, fieldname: str) -> Any: ...
    async def set_value(
        doctype: str,
        id_or_name: str,
        fieldname: str | dict[str, Any],
        value: Any = None,
    ) -> None: ...
    async def get_single(doctype: str, fieldname: str) -> Any: ...
    async def submit(doctype: str, doc_id: str, action: str) -> dict[str, Any]: ...
    async def copy_doc(
        doctype: str,
        id_or_name: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    async def get_meta(doctype: str) -> Any: ...

    # ── Context managers ──────────────────────────────────────────────────────
    def context(
        session: AsyncSession,
        engine: AsyncEngine | None = None,
        user: User | None = None,
    ) -> AbstractAsyncContextManager[None]: ...
    def system_context(
        session: AsyncSession,
        engine: AsyncEngine | None = None,
    ) -> AbstractAsyncContextManager[None]: ...
    def bootstrap_context(
        session: AsyncSession,
        engine: AsyncEngine | None = None,
    ) -> AbstractAsyncContextManager[None]: ...


# Lazy loading to avoid circular imports
def __getattr__(name: str):
    """Lazy load API exports when first accessed."""
    if name == "log":
        from grunt.log import log

        return log

    if name == "log_error":
        from grunt.monitoring.error_log import record_error

        return record_error

    if name in (
        "db",
        "GruntDB",
        "msgprint",
        "msgprint_list",
        "throw",
        "notify",
        "notify_all",
        "queue_email",
        "ApplicationError",
        "get_current_user",
        "add_comment",
        "get_comments",
        "delete_comment",
        "log_activity",
        "get_activity_log",
        "Comment",
        "ActivityEntry",
        "set_session",
        "get_session",
        "set_user",
        "get_user",
        "set_engine",
        "get_engine",
        "set_site",
        "get_site",
        "clear_context",
        "whitelist",
        "get_doc",
        "find_doc",
        "get_doc_instance",
        "get_list",
        "new_doc",
        "save_doc",
        "delete_doc",
        "copy_doc",
        "get_meta",
        "get_values",
        "get_value",
        "set_value",
        "get_all",
        "count",
        "context",
        "system_context",
        "bootstrap_context",
    ):
        from grunt import api

        # Some methods are on grunt.app.grunt instance, some in grunt.api
        if name in (
            "get_doc",
            "find_doc",
            "get_doc_instance",
            "get_list",
            "new_doc",
            "save_doc",
            "delete_doc",
            "copy_doc",
            "get_meta",
            "get_values",
            "get_value",
            "set_value",
            "get_all",
            "count",
            "context",
            "system_context",
            "bootstrap_context",
        ):
            from grunt.app import grunt

            return getattr(grunt, name)

        return getattr(api, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
