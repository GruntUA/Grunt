"""Comments, reminders and bookmarks on a document - HTTP methods (``/api/v1/method/...``).

RPC: grunt.api.v1.document.collaboration.get_comments
RPC: grunt.api.v1.document.collaboration.add_comment
RPC: grunt.api.v1.document.collaboration.delete_comment
RPC: grunt.api.v1.document.collaboration.assign_to_group
RPC: grunt.api.v1.document.collaboration.get_bookmark
RPC: grunt.api.v1.document.collaboration.add_bookmark
RPC: grunt.api.v1.document.collaboration.remove_bookmark
"""

import re
from typing import Any

from fastapi import HTTPException, status

from grunt.api.context import whitelist
from grunt.auth.current import acting_user
from grunt.db.api import GruntDB
from grunt.i18n import _
from grunt.local import user_email
from grunt.notification.events import trigger
from grunt.permissions.groups import MAX_GROUP_NAME, group_emails
from grunt.permissions.guards import doc_guard
from grunt.permissions.perms import has_perm
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session


@whitelist()
async def get_comments(doctype: str, doc_id: str) -> list[dict[str, Any]]:
    """Return all comments for a document."""
    await doc_guard(doctype, doc_id)

    rows = await documents.get_list(
        "Comment",
        filters={"reference_doctype": doctype, "reference_id": doc_id},
        order_by="created_at",
        order="asc",
        limit=500,
    )

    return [
        {
            "name": str(r["name"]),
            "content": r.get("content"),
            "comment_type": r.get("comment_type"),
            "owner": r.get("owner"),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
        }
        for r in rows
    ]


@whitelist()
async def add_comment(
    doctype: str,
    doc_id: str,
    content: str,
    comment_type: str = "Comment",
    parent_comment: str | None = None,
) -> dict[str, Any]:
    """Add a comment to a document. Parses @email mentions and
    ``@[Group name]`` - every active member of the user group.

    ``parent_comment`` makes it a reply; the parent's author is notified.
    """
    content = (content or "").strip()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_("content is required"))

    await doc_guard(doctype, doc_id)

    comment = await documents.new_doc(
        "Comment",
        {
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "content": content,
            "comment_type": comment_type,
            "parent_comment": parent_comment or None,
        },
    )

    # @mention notifications
    mentions = set(re.findall(r"@([\w.+\-]+@[\w.\-]+)", content))
    # The name as written and trimmed - a group saved before names were
    # trimmed (UserGroup.validate) keeps its padded id.
    raw = re.findall(rf"@\[([^\]\n]{{1,{MAX_GROUP_NAME}}})\]", content)
    groups = sorted({g for name in raw for g in (name, name.strip()) if g.strip()})
    mentions |= set(await group_emails(groups))
    mentions.discard(user_email())  # do not notify self
    if mentions:
        await _comment_event("grunt.comment.mentioned", comment, sorted(mentions))

    # Reply: tell the author of the thread's root (unless already @mentioned).
    root = comment.parent_comment
    if root:
        root_author = await _db.get_value("Comment", root, "owner")
        if root_author and root_author != user_email() and root_author not in mentions:
            await _comment_event("grunt.comment.replied", comment, [root_author])

    return comment


@whitelist()
async def assign_to_group(
    doctype: str, doc_id: str, group: str, description: str = ""
) -> dict[str, Any]:
    """Assign the document to every active member of *group* - a ToDo each,
    as if assigned one by one (needs creating ToDos); members it is already
    openly assigned to are skipped. Returns ``{"assigned": [emails]}``."""
    await doc_guard(doctype, doc_id)
    if not await _db.exists("UserGroup", group):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_("User group “%(group)s” not found") % {"group": group},
        )
    taken = set(
        await _db.get_all(
            "ToDo",
            filters={
                "reference_doctype": doctype,
                "reference_id": doc_id,
                "status__in": ["Open", "In Progress"],
            },
            pluck="assigned_to",
            limit=None,
        )
    )
    assigned: list[str] = []
    for email in await group_emails([group]):
        if email in taken:
            continue
        await documents.new_doc(
            "ToDo",
            {
                "reference_doctype": doctype,
                "reference_id": doc_id,
                "assigned_to": email,
                "status": "Open",
                "description": description.strip() or f"Assigned to {email}",
            },
        )
        assigned.append(email)
    return {"assigned": assigned}


async def _comment_event(key: str, comment: dict[str, Any], recipients: list[str]) -> None:
    """Code event *key* about *comment* - opens the commented document."""
    await trigger(
        key,
        doc=dict(comment),
        doctype="Comment",
        link=(comment["reference_doctype"], str(comment["reference_id"])),
        recipients=recipients,
        actor=user_email() or "",
        extra={"text": comment.get("content") or ""},
    )


@whitelist()
async def delete_comment(doctype: str, doc_id: str, comment_id: str) -> None:
    """Delete a comment."""

    comment = await documents.get_doc("Comment", comment_id)
    user = acting_user()
    if comment.owner != user.email and not await has_perm("grunt.moderate_comments"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=_("Not allowed"))

    await documents.delete_doc("Comment", comment_id)


@whitelist()
async def add_reminder(
    doctype: str, doc_id: str, remind_at: str, description: str = ""
) -> dict[str, Any]:
    """Remind the current user about this document at *remind_at*."""
    await doc_guard(doctype, doc_id)
    return await documents.new_doc(
        "Reminder",
        {
            "reference_doctype": doctype,
            "reference_name": doc_id,
            "remind_at": remind_at,
            "description": (description or "").strip() or None,
        },
    )


@whitelist()
async def get_bookmark(doctype: str, doc_id: str) -> dict[str, Any] | None:
    """Return the current user's bookmark."""
    await doc_guard(doctype, doc_id)

    rows = await documents.get_list(
        "Bookmark",
        filters={
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "owner": user_email(),
        },
        limit=1,
    )

    data = dict(rows[0]) if rows else None
    if data and data.get("created_at"):
        data["created_at"] = str(data["created_at"])
    return data


@whitelist()
async def add_bookmark(doctype: str, doc_id: str, title: str = "") -> dict[str, Any]:
    """Bookmark a document."""
    await doc_guard(doctype, doc_id)

    return await documents.new_doc(
        "Bookmark",
        {
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "title": title,
        },
    )


@whitelist()
async def remove_bookmark(doctype: str, doc_id: str) -> None:
    """Remove a bookmark."""

    rows = await documents.get_list(
        "Bookmark",
        filters={
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "owner": user_email(),
        },
        limit=1,
    )
    if rows:
        await documents.delete_doc("Bookmark", rows[0]["name"])
