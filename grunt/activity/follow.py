"""Document following - notify ``DocFollow`` subscribers about changes.

Followers get a notification (bell + web-push) when a followed document is
updated (with the changed fields) or commented on. The author of the change is
never notified about their own action. Follows are dropped with the document.

A user can follow automatically what they create, comment on, are assigned or
get shared (``User.follow_*``, the profile's Preferences tab).
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.auth.constants import SYSTEM_USER_EMAIL
from grunt.db.api import GruntDB
from grunt.document.titles import resolve_reference_titles
from grunt.i18n import _
from grunt.local import system_context
from grunt.log import log
from grunt.notification.events import trigger
lazy from grunt.document.api import documents
lazy from grunt.metadata.registry import doctype_registry

_db = GruntDB()  # stateless: reads through the context's session

# How many changed field labels a notification spells out before "і ще N".
_MAX_FIELDS = 5


async def _followers(doctype: str, doc_id: str, actor_email: str | None) -> list[str]:
    filters: dict[str, Any] = {"reference_doctype": doctype, "reference_id": str(doc_id)}
    if actor_email:
        filters["user__ne"] = actor_email
    return await _db.get_all("DocFollow", filters=filters, pluck="user", limit=None)


async def _doc(doctype: str, doc_id: str) -> dict[str, Any]:
    """The followed document's fields - the rule's recipients and conditions read them."""
    try:
        return dict(await _db.get_doc(doctype, str(doc_id)) or {"name": str(doc_id)})
    except Exception:  # noqa: BLE001 - a virtual / odd DocType: the name is enough
        return {"name": str(doc_id)}


async def _title(doctype: str, doc_id: str) -> str:
    titles = await resolve_reference_titles([(doctype, str(doc_id))])
    return titles.get((doctype, str(doc_id))) or str(doc_id)


def _field_labels(dt: Any, fieldnames: list[str]) -> str:
    fields = getattr(getattr(dt, "doc", dt), "fields", None) or []
    labels = {f.fieldname: _(f.label or f.fieldname) for f in fields}
    shown = [labels.get(f, f) for f in fieldnames[:_MAX_FIELDS]]
    rest = len(fieldnames) - len(shown)
    return ", ".join(shown) + (" " + _("and %(count)s more") % {"count": rest} if rest > 0 else "")


async def notify_followers_of_update(
    *,
    session: AsyncSession,
    doctype: str,
    doc_id: str,
    dt: Any,
    changed_fields: list[str],
    actor_email: str | None,
) -> None:
    """Called from the update pipeline with the fields that actually changed."""
    if not changed_fields or doctype == "DocFollow":
        return
    async with system_context(session):
        users = await _followers(doctype, doc_id, actor_email)
        if not users:
            return
        title = await _title(doctype, doc_id)
        label = getattr(dt, "label", None) or doctype
        doc = await _doc(doctype, doc_id)
    # The followers are the rule's ("Followers"); field labels in their language.
    await trigger(
        "grunt.follow.changed",
        doc=doc,
        doctype=doctype,
        actor=actor_email or "",
        extra={
            "title": title,
            "label": label,
            "fields": lambda: _field_labels(dt, changed_fields),
        },
        session=session,
    )


async def notify_followers_of_comment(
    event: str = "", *, doc: Any = None, user: Any = None, session: Any = None, **kwargs: Any
) -> None:
    """``Comment`` ``after_insert`` hook."""
    if not isinstance(doc, dict) or session is None:
        return
    doctype, doc_id = doc.get("reference_doctype"), doc.get("reference_id")
    if not doctype or not doc_id:
        return

    actor = user or doc.get("owner")  # user: the email of who commented
    async with system_context(session):
        users = await _followers(doctype, doc_id, actor)
        if not users:
            return
        title = await _title(doctype, doc_id)
        target = await _doc(doctype, doc_id)
    await trigger(
        "grunt.follow.commented",
        doc=target,
        doctype=doctype,
        actor=str(actor or ""),
        extra={"title": title, "text": (doc.get("content") or "").strip()},
        session=session,
    )


async def drop_follows(
    event: str = "",
    *,
    doctype: str | None = None,
    doc_id: Any = None,
    doc: Any = None,
    session: Any = None,
    **kwargs: Any,
) -> None:
    """``*`` ``after_delete`` hook - a deleted document has nothing left to follow."""
    ref = doc_id or (doc.get("name") if isinstance(doc, dict) else None)
    if not doctype or not ref or session is None or doctype == "DocFollow":
        return
    async with system_context(session):
        await _db.delete("DocFollow", {"reference_doctype": doctype, "reference_id": str(ref)})


# Auto-follow - the profile's "Follow documents I create / comment on / that are
# assigned / shared to me" (User.follow_*).

# Records about a document, not documents to follow (they have hooks of their own).
_NOT_FOLLOWED = frozenset({"DocFollow", "Comment", "ToDo", "SharedWith"})


async def _wants(user: str | None, flag: str) -> bool:
    if not user:
        return False
    return bool(await _db.get_value("User", {"email": user, "is_active": True}, flag))


async def _followable(doctype: str | None) -> bool:
    if not doctype or doctype in _NOT_FOLLOWED:
        return False
    dt = await doctype_registry.get_meta(doctype)
    return dt is not None and not (dt.is_child or dt.is_singleton or not dt.track_activity)


async def follow(user: str, doctype: str, doc_id: str) -> bool:
    """Make *user* follow the document unless they already do. Returns whether
    a follow was added. Runs as the system (the caller's session)."""
    if not user or not doc_id or not await _followable(doctype):
        return False
    filters = {"reference_doctype": doctype, "reference_id": str(doc_id), "user": user}
    if await _db.exists("DocFollow", filters):
        return False
    await documents.new_doc("DocFollow", filters)
    return True


async def _auto_follow(session: Any, user: Any, flag: str, doctype: Any, doc_id: Any) -> None:
    if session is None or not user or not doc_id or user == SYSTEM_USER_EMAIL:
        return
    try:
        if not await _followable(doctype):
            return
        async with system_context(session):
            if await _wants(str(user), flag):
                await follow(str(user), str(doctype), str(doc_id))
    except Exception:  # noqa: BLE001 - a follow is a nicety; never fail the save
        log.warning("follow.auto_failed", doctype=doctype, flag=flag, exc_info=True)


async def follow_created(
    event: str = "",
    *,
    doctype: str | None = None,
    doc: Any = None,
    user: Any = None,
    session: Any = None,
    **kwargs: Any,
) -> None:
    """``*`` ``after_insert`` hook - the author follows what they created."""
    if isinstance(doc, dict) and doctype not in _NOT_FOLLOWED:
        await _auto_follow(session, user, "follow_created", doctype, doc.get("name"))


async def follow_commented(
    event: str = "", *, doc: Any = None, user: Any = None, session: Any = None, **kwargs: Any
) -> None:
    """``Comment`` ``after_insert`` hook - who commented follows the document."""
    if isinstance(doc, dict):
        await _auto_follow(
            session,
            user or doc.get("owner"),
            "follow_commented",
            doc.get("reference_doctype"),
            doc.get("reference_id"),
        )


async def follow_assigned(
    event: str = "", *, doc: Any = None, session: Any = None, **kwargs: Any
) -> None:
    """``ToDo`` ``after_insert`` / ``after_save`` hook - the assignee follows
    the document the task is about."""
    if isinstance(doc, dict) and doc.get("status") != "Cancelled":
        await _auto_follow(
            session,
            (doc.get("assigned_to") or "").strip(),
            "follow_assigned",
            doc.get("reference_doctype"),
            doc.get("reference_id"),
        )


async def follow_shared(
    event: str = "", *, doc: Any = None, session: Any = None, **kwargs: Any
) -> None:
    """``SharedWith`` ``after_insert`` hook - the person it is shared with
    follows it (not a role, group or everyone)."""
    if isinstance(doc, dict):
        await _auto_follow(
            session,
            doc.get("user"),
            "follow_shared",
            doc.get("reference_doctype"),
            doc.get("reference_id"),
        )
