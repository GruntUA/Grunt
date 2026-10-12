from typing import Any

import grunt
from grunt.activity import attach_titles, attach_user_names, feed_hidden_doctypes
from grunt.document.base import Document


class ActivityLog(Document):
    # NOTE: 'user' is a reserved name in the Document base class.
    # Access this field via self.data.get("user").
    ref_doctype: str
    doc_id: str
    action: str
    details: dict

    async def before_insert(self) -> None:
        # Auto-set 'user' field from request context if caller didn't provide it.
        if not self.data.get("user") and self.user:
            self.data["user"] = self.user.email

    # Helper Classmethods

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
                "ref_doctype": doctype,
                "doc_id": doc_id,
                "action": action,
                "details": details or {},
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
            filters={"ref_doctype": doctype, "doc_id": doc_id},
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
    """Return a filtered, paginated activity feed.

    When browsing the global feed (no explicit ``doctype``/``doc_id`` filter),
    infrastructural doctypes are hidden so business activity is not drowned out
    by config/session/log churn. A per-document timeline (``doc_id`` set) is
    never filtered - it must stay complete.
    """
    filters: dict[str, Any] = {}
    if doctype:
        filters["ref_doctype"] = doctype
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

    # Hide infrastructural doctypes from the global feed only.
    if not doctype and not doc_id:
        hidden = await feed_hidden_doctypes()
        if hidden:
            filters["ref_doctype__nin"] = hidden

    page = int(page)
    per_page = int(per_page)
    total = await grunt.count("ActivityLog", filters=filters)
    entries = await grunt.get_list(
        "ActivityLog",
        filters=filters,
        fields=["name", "ref_doctype", "doc_id", "action", "user", "details", "created_at"],
        limit=per_page,
        page=page,
        order_by=sort_by,
        order=sort_order,
    )

    await attach_titles(entries)
    await attach_user_names(entries)

    return {
        "items": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": -(-total // per_page),
    }
