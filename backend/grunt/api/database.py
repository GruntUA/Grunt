"""Database shortcuts — simpler than Document API for single values.

Example:
    from grunt import db

    # Get one value
    name = await db.get_value("User", "test@example.com", "full_name")

    # Set one value
    await db.set_value("User", "test@example.com", "status", "Active")

    # Count
    active_count = await db.count("User", {"status": "Active"})

    # Check existence
    if await db.exists("User", "test@example.com"):
        print("User exists")
"""

from typing import Any

from sqlalchemy import func, select

from grunt.api.context import get_engine, get_session, get_user
from grunt.core.document.service import DocumentService
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry


class Database:
    """High-level database API."""

    @staticmethod
    async def get_value(doctype: str, doc_id: str, field: str) -> Any:
        """Get a single field value from a document.

        Args:
            doctype: e.g., "User"
            doc_id: The document ID
            field: Field name, e.g., "full_name"

        Returns:
            Field value or None if document/field not found
        """
        try:
            doc = await _get_doc_or_none(doctype, doc_id)
            return doc.get(field) if doc else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    async def set_value(doctype: str, doc_id: str, field: str, value: Any) -> None:
        """Set a single field value and save.

        Args:
            doctype: e.g., "User"
            doc_id: The document ID
            field: Field name
            value: New value
        """
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        doc = await svc.get_document(doctype, doc_id, user)
        doc[field] = value
        await svc.update_document(doctype, doc_id, doc, user)
        await session.flush()

    @staticmethod
    async def exists(doctype: str, doc_id: str) -> bool:
        """Check if a document exists.

        Args:
            doctype: e.g., "User"
            doc_id: The document ID

        Returns:
            True if document exists, False otherwise
        """
        try:
            return await _get_doc_or_none(doctype, doc_id) is not None
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    async def count(doctype: str, filters: dict[str, Any] | None = None) -> int:
        """Count documents matching filters.

        Args:
            doctype: e.g., "Invoice"
            filters: e.g., {"status": "Pending"}

        Returns:
            Count of matching documents
        """
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        # Use list_documents with limit=0 to only count
        docs = await svc.list_documents(doctype, filters or {}, user, limit=1, offset=0)
        count_result = await session.execute(
            select(func.count()).select_from(compile_doctype_to_table(doctype))
        )
        return count_result.scalar() or 0

    @staticmethod
    async def delete(doctype: str, doc_id: str) -> None:
        """Delete a document.

        Args:
            doctype: e.g., "Invoice"
            doc_id: The document ID
        """
        session = get_session()
        engine = get_engine()
        user = get_user()

        svc = DocumentService(session, engine)
        await svc.delete_document(doctype, doc_id, user)
        await session.flush()


async def _get_doc_or_none(doctype: str, doc_id: str) -> dict[str, Any] | None:
    """Helper to get document or None without raising."""
    try:
        session = get_session()
        engine = get_engine()
        user = get_user()
        svc = DocumentService(session, engine)
        return await svc.get_document(doctype, doc_id, user)
    except Exception:  # noqa: BLE001
        return None


# Global instance
db = Database()
