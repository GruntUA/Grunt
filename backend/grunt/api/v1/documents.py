"""Generic Document CRUD whitelisted methods."""

from __future__ import annotations
from typing import Any
import grunt
from grunt.app import grunt as grunt_app

@grunt.whitelist()
async def get_doc(doctype: str, name: str) -> dict[str, Any]:
    """Get a single document."""
    return await grunt_app.get_doc(doctype, name)

@grunt.whitelist()
async def get_list(
    doctype: str, 
    filters: dict[str, Any] | None = None, 
    fields: list[str] | None = None, 
    limit: int = 20,
    page: int = 1,
    order_by: str | None = None,
    order: str = "desc",
    search: str | None = None
) -> dict[str, Any]:
    """Get a list of documents with metadata."""
    from grunt.core.document.service import DocumentService
    session = grunt_app._require_session()
    engine = grunt_app._require_engine()
    svc = DocumentService(session, engine)
    user = grunt_app._require_user()
    
    return await svc.list_documents(
        doctype,
        user,
        page=page,
        per_page=limit,
        sort_by=order_by,
        sort_order=order,
        filters=filters,
        search=search,
        fields=fields,
    )

@grunt.whitelist()
async def save_doc(doctype: str, name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update an existing document."""
    return await grunt_app.save_doc(doctype, name, data)

@grunt.whitelist()
async def new_doc(doctype: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a new document."""
    return await grunt_app.new_doc(doctype, data)

@grunt.whitelist()
async def delete_doc(doctype: str, name: str) -> bool:
    """Delete a document."""
    await grunt_app.delete_doc(doctype, name)
    return True
