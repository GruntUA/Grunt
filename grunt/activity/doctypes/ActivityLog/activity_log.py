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
    """Return a filtered, paginated activity feed.

    When browsing the global feed (no explicit ``doctype``/``doc_id`` filter),
    infrastructural doctypes are hidden so business activity is not drowned out
    by config/session/log churn. A per-document timeline (``doc_id`` set) is
    never filtered — it must stay complete.
    """
    from grunt.activity import FEED_HIDDEN_DOCTYPES

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

    # Hide infrastructural doctypes from the global feed only.
    if not doctype and not doc_id and FEED_HIDDEN_DOCTYPES:
        filters["doctype__nin"] = list(FEED_HIDDEN_DOCTYPES)

    page = int(page)
    per_page = int(per_page)
    total = await grunt.count("ActivityLog", filters=filters)
    entries = await grunt.get_list(
        "ActivityLog",
        filters=filters,
        fields=["name", "doctype", "doc_id", "action", "user", "details", "created_at"],
        limit=per_page,
        page=page,
        order_by=sort_by,
        order=sort_order,
    )

    await _attach_titles(entries)

    return {
        "items": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": -(-total // per_page),
    }


async def _attach_titles(entries: list[dict[str, Any]]) -> None:
    """Resolve a human-readable ``title`` for each entry's referenced document.

    Groups lookups by doctype (one query per doctype, not per row) and falls
    back to the raw ``doc_id`` for deleted docs or doctypes without a title
    field. Mutates ``entries`` in place, adding a ``title`` key.
    """
    from grunt.metadata.registry import doctype_registry

    # Collect the doc_ids we need per doctype.
    by_doctype: dict[str, set[str]] = {}
    for e in entries:
        dt_name = e.get("doctype")
        doc_ref = e.get("doc_id")
        if dt_name and doc_ref:
            by_doctype.setdefault(dt_name, set()).add(doc_ref)

    # doctype -> {doc_id: title}
    resolved: dict[str, dict[str, str]] = {}
    for dt_name, ids in by_doctype.items():
        try:
            dt = await doctype_registry.get(dt_name)
        except Exception:
            continue
        title_field = dt.title_field
        if not title_field or title_field == "name":
            continue
        try:
            rows = await grunt.get_list(
                dt_name,
                filters={"name__in": list(ids)},
                fields=["name", title_field],
                limit=len(ids),
            )
        except Exception:
            continue
        resolved[dt_name] = {r["name"]: r[title_field] for r in rows if r.get(title_field)}

    for e in entries:
        dt_name = e.get("doctype") or ""
        doc_ref = e.get("doc_id") or ""
        e["title"] = resolved.get(dt_name, {}).get(doc_ref) or doc_ref
