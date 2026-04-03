"""High-level Document API for Grunt.

Example:
    from grunt import Doc

    # Get a document
    user = await Doc.get("User", "test@example.com")
    user["status"] = "Active"
    await user.save()

    # Create
    doc = await Doc.create("Contract", {"party": "ABC Inc", "amount": 1000})
    await doc.submit()

    # List
    pending = await Doc.list("Invoice", {"status": "Pending"}, order_by="date")

    # Comments
    await doc.add_comment("Approved for payment")
    comments = await doc.get_comments()
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.api.context import get_engine, get_session, get_user
from grunt.core.document.service import DocumentService

T = TypeVar("T", bound="DocProxy")


class DocProxy:
    """Proxy to a document with auto-context session/user/engine."""

    def __init__(self, doctype: str, data: dict[str, Any]) -> None:
        self.doctype = doctype
        self.data = data
        self._modified = False
        self._session: AsyncSession | None = None

    async def save(self) -> None:
        """Save changes to the document."""
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        self.data = await svc.update_document(self.doctype, self.data.get("id"), self.data, user)
        await session.flush()
        self._modified = False

    async def submit(self) -> None:
        """Submit/lock the document (workflow state transition)."""
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        # Transition to "Submitted" workflow state
        self.data["docstatus"] = 1
        self.data = await svc.update_document(self.doctype, self.data.get("id"), self.data, user)
        await session.flush()

    async def delete(self) -> None:
        """Delete this document."""
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        await svc.delete_document(self.doctype, self.data.get("id"), user)
        await session.flush()

    async def add_comment(self, text: str, is_private: bool = False) -> Any:
        """Add a comment to this document.

        Args:
            text: Comment text
            is_private: If True, only visible to creator and superadmin
        """
        from grunt.api.activity import add_comment  # noqa: PLC0415

        return await add_comment(self.doctype, self.data.get("id"), text, is_private)

    async def get_comments(self) -> list[Any]:
        """Get all comments on this document.

        Returns:
            List of Comment objects
        """
        from grunt.api.activity import get_comments  # noqa: PLC0415

        return await get_comments(self.doctype, self.data.get("id"))

    def __getitem__(self, key: str) -> Any:
        """Get field value: doc["name"]"""
        return self.data.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Set field value: doc["status"] = "active" """
        self.data[key] = value
        self._modified = True

    def __repr__(self) -> str:
        return f"<DocProxy {self.doctype} {self.data.get('id', 'NEW')}>"


class Doc:
    """High-level Document API (static methods)."""

    @staticmethod
    async def get(doctype: str, doc_id: str) -> DocProxy:
        """Get a document by ID.

        Args:
            doctype: e.g., "User", "Contract"
            doc_id: The document ID/name

        Returns:
            DocProxy with document data

        Raises:
            DocumentNotFound if document doesn't exist
        """
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        data = await svc.get_document(doctype, doc_id, user)
        return DocProxy(doctype, data)

    @staticmethod
    async def create(doctype: str, data: dict[str, Any] | None = None) -> DocProxy:
        """Create a new document.

        Args:
            doctype: e.g., "Invoice"
            data: Field values dict, e.g. {"party": "ABC", "amount": 1000}

        Returns:
            DocProxy with new document
        """
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        doc_data = await svc.create_document(doctype, data or {}, user)
        return DocProxy(doctype, doc_data)

    @staticmethod
    async def list(
        doctype: str,
        filters: dict[str, Any] | None = None,
        order_by: str = "name",
        limit: int = 100,
        offset: int = 0,
    ) -> list[DocProxy]:
        """List documents with filters.

        Args:
            doctype: e.g., "Invoice"
            filters: {"status": "Pending", "date__gte": "2024-01-01"}
            order_by: Field name, e.g. "date" or "name"
            limit: Max results (default 100)
            offset: Pagination offset

        Returns:
            List of DocProxy objects
        """
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        docs = await svc.list_documents(
            doctype,
            filters or {},
            user,
            order_by=order_by,
            limit=limit,
            offset=offset,
        )
        return [DocProxy(doctype, d) for d in docs]

    @staticmethod
    async def exists(doctype: str, doc_id: str) -> bool:
        """Check if a document exists."""
        try:
            await Doc.get(doctype, doc_id)
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    async def delete(doctype: str, doc_id: str) -> None:
        """Delete a document by ID."""
        doc = await Doc.get(doctype, doc_id)
        await doc.delete()

    @staticmethod
    async def set_value_batch(
        doctype: str,
        field: str,
        value: Any,
        doc_ids: list[str],
    ) -> int:
        """Set the same field value for multiple documents (batch operation).

        Args:
            doctype: e.g., "Invoice"
            field: Field name to update
            value: Value to set
            doc_ids: List of document IDs

        Returns:
            Number of documents updated

        Example:
            count = await Doc.set_value_batch(
                "Invoice",
                "status",
                "Paid",
                ["INV-001", "INV-002", "INV-003"]
            )
            print(f"Updated {count} invoices")
        """
        from grunt.api.database import db  # noqa: PLC0415

        count = 0
        for doc_id in doc_ids:
            try:
                await db.set_value(doctype, doc_id, field, value)
                count += 1
            except Exception:  # noqa: BLE001
                # Continue with other documents on error
                continue

        return count

    @staticmethod
    async def delete_many(doctype: str, doc_ids: list[str]) -> int:
        """Delete multiple documents (batch operation).

        Args:
            doctype: e.g., "Invoice"
            doc_ids: List of document IDs to delete

        Returns:
            Number of documents deleted

        Example:
            count = await Doc.delete_many("Invoice", ["INV-001", "INV-002"])
            print(f"Deleted {count} invoices")
        """
        count = 0
        for doc_id in doc_ids:
            try:
                await Doc.delete(doctype, doc_id)
                count += 1
            except Exception:  # noqa: BLE001
                # Continue with other documents on error
                continue

        return count

