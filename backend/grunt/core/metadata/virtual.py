"""Virtual DocType adapter — base class for DocTypes backed by external data sources.

A Virtual DocType has `is_virtual=True` and does NOT create a database table.
Instead, the developer implements a controller class that inherits from
`VirtualDocType` and overrides the CRUD methods.

Usage:
    # In controllers/external_customer.py
    class ExternalCustomer(VirtualDocType):
        async def get_list(self, filters, page, per_page, **kwargs):
            return await my_external_api.list_customers(...)

        async def get(self, doc_id):
            return await my_external_api.get_customer(doc_id)

        async def create(self, data):
            return await my_external_api.create_customer(data)
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class VirtualDocType:
    """Base class for Virtual DocType controllers.

    Override the CRUD methods to provide data from any external source
    (REST API, gRPC, 1С, GraphQL, file system, etc.).

    All methods receive the raw request data and should return dicts
    matching the DocType field structure.
    """

    def __init__(self, doctype: str, user: Any = None) -> None:
        self.doctype = doctype
        self.user = user

    async def get_list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "name",
        sort_order: str = "desc",
        search: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return a paginated list of documents.

        Must return: {"data": [...], "meta": {"total": N, "page": N, "per_page": N}}
        """
        raise NotImplementedError(
            f"Virtual DocType '{self.doctype}' must implement get_list()"
        )

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        """Return a single document by ID.

        Must return a dict matching the DocType fields.
        """
        raise NotImplementedError(
            f"Virtual DocType '{self.doctype}' must implement get()"
        )

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Create a new document.

        Returns the created document dict.
        """
        raise NotImplementedError(
            f"Virtual DocType '{self.doctype}' must implement create()"
        )

    async def update(
        self, doc_id: str, data: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Update an existing document.

        Returns the updated document dict.
        """
        raise NotImplementedError(
            f"Virtual DocType '{self.doctype}' must implement update()"
        )

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        """Delete a document by ID."""
        raise NotImplementedError(
            f"Virtual DocType '{self.doctype}' must implement delete()"
        )

    async def get_count(
        self, filters: dict[str, Any] | None = None, **kwargs: Any
    ) -> int:
        """Return the total count of documents matching filters.

        Default implementation calls get_list and reads meta.total.
        Override for efficiency.
        """
        result = await self.get_list(filters=filters, page=1, per_page=1, **kwargs)
        return result.get("meta", {}).get("total", 0)
