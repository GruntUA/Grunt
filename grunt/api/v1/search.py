"""Global full-text search API — whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt


@grunt.whitelist()
async def global_search(
    q: str,
    doctype: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not q or not q.strip():
        grunt.throw("Parameter 'q' is required", "VALIDATION_ERROR")

    limit = int(limit)
    if limit <= 0:
        grunt.throw("Parameter 'limit' must be positive", "VALIDATION_ERROR")
    if limit > 50:
        grunt.throw("Parameter 'limit' too high", "VALIDATION_ERROR")

    from grunt.app import grunt as grunt_app
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.rbac import permission_checker
    from grunt.search.service import search_index_service

    raw = await search_index_service.search(
        session=grunt_app._require_session(),
        q=q,
        limit=limit,
        doctype=doctype,
    )

    user = grunt_app._require_user()

    # Check read permission per doctype
    allowed_doctypes: dict[str, bool] = {}
    results = []

    for r in raw:
        dt_name = r["doctype"]
        if dt_name not in allowed_doctypes:
            try:
                dt = await doctype_registry.get(dt_name)
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


@grunt.whitelist()
async def rebuild_index() -> dict[str, Any]:
    """Rebuild the entire search index from scratch. Superadmin only."""
    from grunt.app import grunt as grunt_app
    from grunt.search.service import search_index_service

    # Manual permission check for superadmin
    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt.throw("Not authorized", "PERMISSION_DENIED")

    session = grunt_app._require_session()
    count = await search_index_service.reindex_all(session, grunt_app._require_engine())
    return {"indexed": count}
