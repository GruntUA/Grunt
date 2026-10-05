"""Global full-text search API - whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt import _


@grunt.whitelist()
async def global_search(
    q: str,
    doctype: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not q or not q.strip():
        grunt.throw(_("Parameter 'q' is required"), "VALIDATION_ERROR")

    limit = int(limit)
    if limit <= 0:
        grunt.throw(_("Parameter 'limit' must be positive"), "VALIDATION_ERROR")
    if limit > 50:
        grunt.throw(_("Parameter 'limit' too high"), "VALIDATION_ERROR")

    from grunt.permissions.rbac import permission_checker
    from grunt.search.service import search_index_service

    raw = await search_index_service.search(
        session=grunt.get_session(),
        q=q,
        limit=limit,
        doctype=doctype,
    )

    user = grunt.get_user()

    # Check read permission per doctype
    allowed_doctypes: dict[str, bool] = {}
    results = []

    for r in raw:
        dt_name = r["doctype"]
        if dt_name not in allowed_doctypes:
            dt = await grunt.get_meta(dt_name)
            if dt is None:
                allowed_doctypes[dt_name] = False
            else:
                try:
                    allowed_doctypes[dt_name] = await permission_checker.check(user, dt, "read")
                except Exception:
                    allowed_doctypes[dt_name] = False

        if allowed_doctypes.get(dt_name):
            results.append(
                {
                    "doctype": r["doctype"],
                    "name": r["doc_id"],
                    "display_title": r.get("title") or r.get("doc_name", ""),
                    "module": r.get("module", ""),
                }
            )

    return results


@grunt.whitelist(roles=["System Manager"])
async def rebuild_index() -> dict[str, Any]:
    """Rebuild the entire search index from scratch. System Manager only."""
    from grunt.search.service import search_index_service

    session = grunt.get_session()
    count = await search_index_service.reindex_all(session, grunt.get_engine())
    return {"indexed": count}
