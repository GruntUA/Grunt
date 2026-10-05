from typing import Any

import grunt
from grunt.activity import feed_hidden_doctypes
from grunt.document.base import Document
from grunt.document.titles import resolve_reference_titles


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
    never filtered - it must stay complete.
    """
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
    if not doctype and not doc_id:
        hidden = await feed_hidden_doctypes()
        if hidden:
            filters["doctype__nin"] = hidden

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
    await _attach_user_names(entries)

    return {
        "items": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": -(-total // per_page),
    }


async def _attach_titles(entries: list[dict[str, Any]]) -> None:
    """Resolve a human-readable ``title`` for each entry's referenced document.

    Falls back to the raw ``doc_id`` for deleted docs or doctypes without a
    title field. Mutates ``entries`` in place, adding a ``title`` key.
    """
    refs = [(e["doctype"], e["doc_id"]) for e in entries if e.get("doctype") and e.get("doc_id")]
    titles = await resolve_reference_titles(refs)

    for e in entries:
        dt_name = e.get("doctype") or ""
        doc_ref = e.get("doc_id") or ""
        e["title"] = titles.get((dt_name, doc_ref)) or doc_ref


async def _attach_user_names(entries: list[dict[str, Any]]) -> None:
    """Resolve each entry's ``user`` (an email) to the account's ``full_name``.

    Mutates ``entries`` in place, adding a ``user_name`` key. Falls back to the
    raw email when the account no longer exists or has no name set.

    Runs as SYSTEM_USER: the ``User`` doctype's "All" role can only read its
    own row (``match: name == user``), and the activity feed must show every
    author's name to every viewer, not just the viewer's own.
    """
    emails = {e["user"] for e in entries if e.get("user")}
    if not emails:
        return

    async with grunt.system_context(grunt.get_session()):
        rows = await grunt.get_list(
            "User",
            filters={"name__in": list(emails)},
            fields=["name", "full_name"],
            limit=len(emails),
        )
    names = {r["name"]: r["full_name"] for r in rows if r.get("full_name")}

    for e in entries:
        email = e.get("user") or ""
        e["user_name"] = names.get(email) or email
