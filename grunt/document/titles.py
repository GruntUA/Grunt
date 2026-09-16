"""Batch-resolve (doctype, id) references to human-readable titles.

Shared by activity feeds, workspace widgets, and anywhere else that needs to
turn a raw document reference into a display label without one query per row.
"""

from __future__ import annotations

from grunt.log import log


async def resolve_reference_titles(
    refs: list[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    """Resolve (doctype, id) references to display titles, one query per doctype.

    Doctypes that no longer exist, or whose title lookup fails, are skipped —
    callers fall back to the raw id for those refs.
    """
    from grunt.app import grunt

    by_doctype: dict[str, set[str]] = {}
    for dt_name, doc_id in refs:
        if dt_name and doc_id:
            by_doctype.setdefault(dt_name, set()).add(doc_id)

    titles: dict[tuple[str, str], str] = {}
    for dt_name, ids in by_doctype.items():
        dt = await grunt.get_meta(dt_name)
        if dt is None:
            log.debug("titles.doctype_not_found", doctype=dt_name)
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
            log.debug("titles.title_lookup_failed", doctype=dt_name)
            continue
        for r in rows:
            if r.get(title_field):
                titles[(dt_name, r["name"])] = r[title_field]
    return titles
