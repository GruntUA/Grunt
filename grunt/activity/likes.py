"""Likes and the per-row badges of list views (age, comments, likes - as in Frappe).

A like is a ``DocLike`` row (one per user and document). The list view asks for
the badges of the whole page in one call; documents the caller cannot read are
left out, so the counts never leak through ids picked by hand.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

import grunt
from grunt.permissions.guards import doc_guard

# One list page at most - larger requests are cut, not rejected.
_MAX_IDS = 500


async def _counts(doctype: str, ref_doctype: str, ids: list[str], **filters: Any) -> dict[str, int]:
    """``{reference_id: rows}`` of *doctype* pointing at *ids* of *ref_doctype*."""
    dt = await grunt.get_meta(doctype)
    if dt is None:
        return {}
    t = dt.table
    stmt = (
        select(t.c.reference_id, func.count())
        .where(t.c.reference_doctype == ref_doctype, t.c.reference_id.in_(ids))
        .group_by(t.c.reference_id)
    )
    for column, value in filters.items():
        stmt = stmt.where(t.c[column] == value)
    rows = (await grunt.get_session().execute(stmt)).all()
    return {str(ref): int(n) for ref, n in rows}


@grunt.whitelist()
async def get_list_badges(doctype: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """``{id: {"comments": n, "likes": n, "liked": bool}}`` for one page of a list."""
    ids = [str(i) for i in ids[:_MAX_IDS]]
    if not ids:
        return {}
    readable = await grunt.get_list(
        doctype, filters={"name__in": ids}, fields=["name"], limit=len(ids), include_total=False
    )
    ids = [str(r["name"]) for r in readable]
    if not ids:
        return {}

    me = grunt.get_user().email
    async with grunt.system_context(grunt.get_session()):
        comments = await _counts("Comment", doctype, ids, comment_type="Comment")
        likes = await _counts("DocLike", doctype, ids)
        mine = set(
            await grunt.db.get_all(
                "DocLike",
                filters={"reference_doctype": doctype, "reference_id__in": ids, "user": me},
                pluck="reference_id",
                limit=None,
            )
        )
    return {
        i: {"comments": comments.get(i, 0), "likes": likes.get(i, 0), "liked": i in mine}
        for i in ids
    }


@grunt.whitelist()
async def toggle_like(doctype: str, doc_id: str) -> dict[str, Any]:
    """Like the document, or take the like back. Returns ``{"liked", "likes"}``."""
    await doc_guard(doctype, doc_id)
    me = grunt.get_user().email
    ref = {"reference_doctype": doctype, "reference_id": str(doc_id)}
    async with grunt.system_context(grunt.get_session()):
        existing = await grunt.db.get_all(
            "DocLike", filters={**ref, "user": me}, pluck="name", limit=1
        )
    if existing:
        await grunt.delete_doc("DocLike", str(existing[0]))
    else:
        await grunt.new_doc("DocLike", ref)
    async with grunt.system_context(grunt.get_session()):
        likes = await grunt.db.count("DocLike", ref)
    return {"liked": not existing, "likes": likes}


async def drop_likes(
    event: str = "",
    *,
    doctype: str | None = None,
    doc_id: Any = None,
    doc: Any = None,
    session: Any = None,
    **kwargs: Any,
) -> None:
    """``*`` ``after_delete`` hook - likes go with the document."""
    ref = doc_id or (doc.get("name") if isinstance(doc, dict) else None)
    if not doctype or not ref or session is None or doctype == "DocLike":
        return
    async with grunt.system_context(session):
        await grunt.db.delete("DocLike", {"reference_doctype": doctype, "reference_id": str(ref)})
