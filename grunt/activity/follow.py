"""Document following - notify ``DocFollow`` subscribers about changes.

Followers get a notification (bell + web-push) when a followed document is
updated (with the changed fields) or commented on. The author of the change is
never notified about their own action. Follows are dropped with the document.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.db.api import GruntDB
from grunt.document.titles import resolve_reference_titles
from grunt.i18n import _
from grunt.local import system_context
from grunt.notification.events import trigger

_db = GruntDB()  # stateless: reads through the context's session

# How many changed field labels a notification spells out before "і ще N".
_MAX_FIELDS = 5


async def _followers(doctype: str, doc_id: str, actor_email: str | None) -> list[str]:
    filters: dict[str, Any] = {"reference_doctype": doctype, "reference_id": str(doc_id)}
    if actor_email:
        filters["user__ne"] = actor_email
    return await _db.get_all("DocFollow", filters=filters, pluck="user", limit=None)


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
    # The followers are the rule's ("Followers"); field labels in their language.
    await trigger(
        "grunt.follow.changed",
        doc={"name": str(doc_id)},
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
    await trigger(
        "grunt.follow.commented",
        doc={"name": str(doc_id)},
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
