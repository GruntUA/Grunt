from typing import Any

import grunt
from grunt.document.base import Document


class ActivityLog(Document):
    # NOTE: 'doctype' and 'user' are reserved names in Document base class.
    # Access these fields via self.data.get("doctype") / self.data.get("user").
    doc_id: str
    action: str
    details: dict

    async def before_insert(self) -> None:
        # Auto-set 'user' field from request context if caller didn't provide it.
        if not self.data.get("user") and self.user:
            self.data["user"] = self.user.email

    # ------------------------------------------------------------------
    # Helper Classmethods
    # ------------------------------------------------------------------

    @classmethod
    async def log(
        cls,
        doctype: str,
        doc_id: str,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log an activity entry. Controller auto-fills user from context."""
        return await grunt.new_doc(
            "ActivityLog",
            {
                "doctype": doctype,
                "doc_id": doc_id,
                "action": action,
                "details": details,
            },
        )

    @classmethod
    async def get_log(
        cls,
        doctype: str,
        doc_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get activity log for a document (newest first)."""
        return await grunt.get_list(
            "ActivityLog",
            filters={"doctype": doctype, "doc_id": doc_id},
            order_by="created_at",
            order="desc",
            limit=limit,
        )


@grunt.whitelist()
async def list_activity(
    page: int = 1,
    per_page: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    doctype: str | None = None,
    doc_id: str | None = None,
    user: str | None = None,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Return a filtered, paginated activity feed."""
    filters: dict[str, Any] = {}
    if doctype:
        filters["doctype"] = doctype
    if doc_id:
        filters["doc_id"] = doc_id
    if user:
        filters["user"] = user
    if action:
        filters["action"] = action
    if date_from:
        filters["created_at__gte"] = date_from
    if date_to:
        filters["created_at__lte"] = date_to

    page = int(page)
    per_page = int(per_page)
    total = await grunt.count("ActivityLog", filters=filters)
    entries = await grunt.get_list(
        "ActivityLog",
        filters=filters,
        fields=["id", "doctype", "doc_id", "action", "user", "details", "created_at"],
        limit=per_page,
        page=page,
        order_by=sort_by,
        order=sort_order,
    )

    return {
        "items": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": -(-total // per_page),
    }
