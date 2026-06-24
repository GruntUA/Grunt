"""DocumentService — thin adapter over the stateful :class:`Document` pipeline.

The CRUD pipeline lives on :class:`~grunt.document.base.Document` (composed from
``DocumentReadMixin``/``DocumentWriteMixin``). This service is a thin,
session/engine-scoped delegator kept for backward compatibility: callers that
work with plain dicts (the GruntApp facade, REST routes, tests) keep their exact
signatures while the real logic runs on the document object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User
    from grunt.document.base import Document, DocumentList

logger = structlog.get_logger()


class DocumentService:
    """Dict-based CRUD facade delegating to the :class:`Document` pipeline."""

    def __init__(self, session: AsyncSession, engine: AsyncEngine) -> None:
        self.session = session
        self.engine = engine

    def _host(self) -> Document:
        """Build a session/engine-bound host document to run pipeline methods on."""
        from grunt.document.base import Document

        doc = Document("", {}, session=self.session, engine=self.engine)
        doc._bind()
        return doc

    async def get_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: User,
        expand: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._host().get_document(doctype_name, doc_id, user, expand=expand)

    async def list_documents(self, doctype_name: str, user: User, **kwargs: Any) -> DocumentList:
        from grunt.document import collection

        return await collection.list_documents(self.session, doctype_name, user, **kwargs)

    async def create_document(
        self,
        doctype_name: str,
        data: dict[str, Any],
        user: User,
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        return await self._host().create_document(
            doctype_name, data, user, ignore_required=ignore_required
        )

    async def update_document(
        self,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
        user: User,
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        return await self._host().update_document(
            doctype_name, doc_id, data, user, ignore_required=ignore_required
        )

    async def delete_document(self, doctype_name: str, doc_id: str, user: User) -> None:
        await self._host().delete_document(doctype_name, doc_id, user)

    async def bulk_delete(
        self,
        doctype_name: str,
        ids: list[str],
        user: User,
        progress_cb: Any | None = None,
    ) -> tuple[int, list[str]]:
        from grunt.document import collection

        return await collection.bulk_delete(
            self.session, self.engine, doctype_name, ids, user, progress_cb=progress_cb
        )

    async def rename_document(
        self, doctype_name: str, old_id: str, new_id: str, user: User
    ) -> dict[str, Any]:
        from grunt.document import collection

        return await collection.rename_document(
            self.session, self.engine, doctype_name, old_id, new_id, user
        )
