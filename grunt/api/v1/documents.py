"""Generic Document CRUD whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt.api.v1.docs.utils import default_sort


@grunt.whitelist()
async def get_doc(
    doctype: str,
    name: str,
    expand: list[str] | None = None,
) -> dict[str, Any]:
    """Get a single document."""
    return await grunt.get_doc(doctype, name, expand=expand)


@grunt.whitelist()
async def get_list(
    doctype: str,
    filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    limit: int = 20,
    page: int = 1,
    order_by: str | None = None,
    order: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Get a list of documents with metadata."""
    order_by, order = await default_sort(doctype, order_by, order)
    res = await grunt.get_list(
        doctype,
        filters=filters,
        fields=fields,
        limit=limit,
        page=page,
        order_by=order_by,
        order=order,
        search=search,
    )
    return res.to_dict()


@grunt.whitelist()
async def save_doc(doctype: str, name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update an existing document."""
    return await grunt.save_doc(doctype, name, data)


@grunt.whitelist()
async def new_doc(doctype: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a new document."""
    return await grunt.new_doc(doctype, data)


@grunt.whitelist()
async def delete_doc(doctype: str, name: str, replace_with: str | None = None) -> bool:
    """Delete a document.

    ``replace_with`` repoints every reference to the deleted document at this
    surviving document of the same DocType before removal.
    """
    await grunt.delete_doc(doctype, name, replace_with)
    return True


@grunt.whitelist()
async def rename_doc(doctype: str, name: str, new_name: str) -> dict[str, Any]:
    """Rename a document."""
    return await grunt.rename_doc(doctype, name, new_name)
