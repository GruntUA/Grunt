"""Document following — notify ``DocFollow`` subscribers about changes.

Followers get a notification (bell + web-push) when a followed document is
updated (with the changed fields) or commented on. The author of the change is
never notified about their own action. Follows are dropped with the document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grunt
from grunt import _, log
from grunt.i18n import language_of, use_language

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

# How many changed field labels a notification spells out before "і ще N".
_MAX_FIELDS = 5


async def _followers(doctype: str, doc_id: str, actor_email: str | None) -> list[str]:
    filters: dict[str, Any] = {"reference_doctype": doctype, "reference_id": str(doc_id)}
    if actor_email:
        filters["user__ne"] = actor_email
    return await grunt.db.get_all("DocFollow", filters=filters, pluck="user", limit=None)


async def _title(doctype: str, doc_id: str) -> str:
    from grunt.document.titles import resolve_reference_titles

    titles = await resolve_reference_titles([(doctype, str(doc_id))])
    return titles.get((doctype, str(doc_id))) or str(doc_id)


def _field_labels(dt: Any, fieldnames: list[str]) -> str:
    fields = getattr(getattr(dt, "doc", dt), "fields", None) or []
    labels = {f.fieldname: _(f.label or f.fieldname) for f in fields}
    shown = [labels.get(f, f) for f in fieldnames[:_MAX_FIELDS]]
    rest = len(fieldnames) - len(shown)
    return ", ".join(shown) + (" " + _("and %(count)s more") % {"count": rest} if rest > 0 else "")


async def _notify(
    session: AsyncSession,
    doctype: str,
    doc_id: str,
    users: list[str],
    compose: Callable[[], tuple[str, str]],
) -> None:
    """Notify each follower; *compose* → ``(subject, message)`` runs in their language."""
    from grunt.notification.service import notification_service

    for user in users:
        try:
            with use_language(await language_of(user)):
                subject, message = compose()
            await notification_service.notify(
                session,
                user=user,
                doctype=doctype,
                doc_id=str(doc_id),
                subject=subject,
                message=message,
            )
        except Exception:
            log.exception("follow.notify_failed", doctype=doctype, doc_id=doc_id, user=user)


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
    async with grunt.system_context(session):
        users = await _followers(doctype, doc_id, actor_email)
        if not users:
            return
        title = await _title(doctype, doc_id)
        label = getattr(dt, "label", None) or doctype
        await _notify(
            session,
            doctype,
            doc_id,
            users,
            lambda: (
                _("%(doctype)s “%(title)s” changed") % {"doctype": _(label), "title": title},
                _("Changed: %(fields)s") % {"fields": _field_labels(dt, changed_fields)}
                + (f" — {actor_email}" if actor_email else ""),
            ),
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

    actor = getattr(user, "email", None) or doc.get("owner")
    async with grunt.system_context(session):
        users = await _followers(doctype, doc_id, actor)
        if not users:
            return
        title = await _title(doctype, doc_id)
        text = (doc.get("content") or "").strip()
        await _notify(
            session,
            doctype,
            doc_id,
            users,
            lambda: (
                _("New comment: “%(title)s”") % {"title": title},
                (f"{actor}: " if actor else "") + (text[:300] if text else ""),
            ),
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
    """``*`` ``after_delete`` hook — a deleted document has nothing left to follow."""
    ref = doc_id or (doc.get("name") if isinstance(doc, dict) else None)
    if not doctype or not ref or session is None or doctype == "DocFollow":
        return
    async with grunt.system_context(session):
        await grunt.db.delete("DocFollow", {"reference_doctype": doctype, "reference_id": str(ref)})
