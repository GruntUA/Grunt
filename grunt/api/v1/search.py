"""Global full-text search API - whitelisted methods."""

from typing import Any

from grunt.api.context import whitelist
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import require_engine, require_session
from grunt.log import log
from grunt.search.service import search_index_service
lazy from grunt.document.api import documents

_OVERFETCH = 4
_MAX_FETCH = 200


@whitelist()
async def global_search(
    q: str,
    doctype: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not q or not q.strip():
        throw(_("Parameter 'q' is required"), "VALIDATION_ERROR")

    limit = int(limit)
    if limit <= 0:
        throw(_("Parameter 'limit' must be positive"), "VALIDATION_ERROR")
    if limit > 50:
        throw(_("Parameter 'limit' too high"), "VALIDATION_ERROR")

    # Over-fetch: hits the user may not read are dropped below, and they must
    # not eat into the page the user asked for.
    raw = await search_index_service.search(
        session=require_session(),
        q=q,
        limit=min(limit * _OVERFETCH, _MAX_FETCH),
        doctype=doctype,
    )

    # One permission-checked read per DocType in the hits: grunt.get_list
    # applies the DocType-level read check *and* every row-level rule
    # (owner/match permissions, User Permissions, list_filter_extra), so a
    # user only ever sees titles of documents they could open.
    ids_by_doctype: dict[str, list[str]] = {}
    for r in raw:
        ids_by_doctype.setdefault(r["doctype"], []).append(r["doc_id"])
    readable: dict[str, set[str]] = {
        dt_name: await _readable_ids(dt_name, ids) for dt_name, ids in ids_by_doctype.items()
    }

    results = []
    for r in raw:
        if r["doc_id"] not in readable[r["doctype"]]:
            continue
        results.append(
            {
                "doctype": r["doctype"],
                "name": r["doc_id"],
                "display_title": r.get("title") or r.get("doc_name", ""),
                "module": r.get("module", ""),
            }
        )
        if len(results) >= limit:
            break

    return results


async def _readable_ids(doctype: str, ids: list[str]) -> set[str]:
    """The subset of *ids* the current user may read (empty on any denial)."""
    try:
        rows = await documents.get_list(
            doctype,
            filters={"name__in": ids},
            fields=["name"],
            limit=len(ids),
            include_total=False,
        )
    except Exception as e:
        log.debug("global_search.doctype_skipped", doctype=doctype, reason=str(e))
        return set()
    return {str(row["name"]) for row in rows}


@whitelist(perm="grunt.manage_doctypes")
async def rebuild_index() -> dict[str, Any]:
    """Rebuild the entire search index from scratch. System Manager only."""
    session = require_session()
    count = await search_index_service.reindex_all(session, require_engine())
    return {"indexed": count}
