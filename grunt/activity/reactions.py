"""Emoji reactions on comments (``CommentReaction``, one row per user, comment and emoji).

The choices come from ``SystemSettings.comment_reactions`` (space-separated);
an empty setting turns reactions off. The timeline gets the summaries with its
comments (``reactions_for``), so reading them needs no extra round trip.
"""

from typing import Any

from grunt.api.context import whitelist
from grunt.db.api import GruntDB
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import require_session, system_context, user_email
from grunt.permissions.guards import doc_guard
from grunt.site.settings import get_setting
lazy from grunt.auth.users import get_users_by_emails
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session

DEFAULT_REACTIONS = "👍 ✅ ❓ 🎉 👀"


async def reaction_choices() -> list[str]:
    raw = await get_setting("comment_reactions", DEFAULT_REACTIONS)
    return list(dict.fromkeys(str(raw or "").split()))


@whitelist()
async def get_reaction_choices() -> list[str]:
    return await reaction_choices()


async def reactions_for(comment_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """``{comment: [{"emoji", "count", "mine", "users"}]}`` in the order of the choices.

    ``users`` are display names, oldest reaction first.

    The caller has already checked access to the document the comments belong to.
    """
    if not comment_ids:
        return {}
    async with system_context(require_session()):
        rows = await _db.get_all(
            "CommentReaction",
            filters={"comment__in": comment_ids},
            fields=["comment", "emoji", "user"],
            order_by="created_at",
            order="asc",
            limit=None,
        )
    me = user_email()
    order = {e: i for i, e in enumerate(await reaction_choices())}
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        chip = grouped.setdefault(str(r["comment"]), {}).setdefault(
            r["emoji"], {"emoji": r["emoji"], "count": 0, "mine": False, "users": []}
        )
        chip["count"] += 1
        chip["mine"] = chip["mine"] or r["user"] == me
        chip["users"].append(r["user"])
    if rows:
        emails = list({r["user"] for r in rows})
        users = await get_users_by_emails(emails, fields=["email", "full_name"])
        names = {u.email: getattr(u, "full_name", None) for u in users}
        for chips in grouped.values():
            for chip in chips.values():
                chip["users"] = [names.get(u) or u for u in chip["users"]]
    return {
        cid: sorted(chips.values(), key=lambda c: order.get(c["emoji"], len(order)))
        for cid, chips in grouped.items()
    }


@whitelist()
async def toggle_reaction(comment: str, emoji: str) -> list[dict[str, Any]]:
    """Add the reaction, or take it back. Returns the comment's reactions afterwards."""
    async with system_context(require_session()):
        ref = await _db.get_value(
            "Comment", comment, ["reference_doctype", "reference_id"], as_dict=True
        )
    if ref is None:
        throw(_("Comment not found"), "NOT_FOUND")
    await doc_guard(ref.reference_doctype, ref.reference_id)

    key = {"comment": comment, "emoji": emoji, "user": user_email()}
    async with system_context(require_session()):
        existing = await _db.get_all("CommentReaction", filters=key, pluck="name", limit=1)
    if existing:
        await documents.delete_doc("CommentReaction", str(existing[0]))
    else:
        await documents.new_doc("CommentReaction", {"comment": comment, "emoji": emoji})
    return (await reactions_for([comment])).get(comment, [])


async def drop_reactions(
    event: str = "",
    *,
    doctype: str | None = None,
    doc_id: Any = None,
    doc: Any = None,
    session: Any = None,
    **kwargs: Any,
) -> None:
    """``*`` ``after_delete`` hook - a comment's reactions go with it."""
    ref = doc_id or (doc.get("name") if isinstance(doc, dict) else None)
    if doctype != "Comment" or not ref or session is None:
        return
    async with system_context(session):
        await _db.delete("CommentReaction", {"comment": str(ref)})
