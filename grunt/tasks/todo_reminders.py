"""Daily reminder for open ToDos whose ``due_date`` has arrived or passed.

One digest notification (bell + email) per assignee, listing their due-today
and overdue tasks. Runs from the framework scheduler - see
``grunt.tasks.scheduler._register_framework_jobs``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

import grunt
from grunt import _, log
from grunt.i18n import language_of, ngettext, use_language
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task

_OPEN_STATES = ["Open", "In Progress"]


@retryable_task()
async def send_due_reminders() -> None:
    """Notify each assignee about their tasks due today or already overdue."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    today = datetime.now(UTC).date()

    async with maker() as session, grunt.system_context(session, eng):
        todos = await grunt.db.get_all(
            "ToDo",
            filters={"status__in": _OPEN_STATES, "due_date__lte": today.isoformat()},
            fields=[
                "name",
                "description",
                "reference_doctype",
                "reference_id",
                "assigned_to",
                "due_date",
            ],
            limit=5000,
        )
        todos = [t for t in todos if (t.get("assigned_to") or "").strip()]
        if not todos:
            log.info("todo_reminders.none_due")
            return

        from grunt.document.titles import resolve_reference_titles

        titles = await resolve_reference_titles(
            [(t.get("reference_doctype") or "", t.get("reference_id") or "") for t in todos]
        )

        by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for t in todos:
            by_user[t["assigned_to"].strip()].append(t)

        from grunt.notification.service import notification_service

        for user, items in by_user.items():
            overdue = sum(1 for t in items if _as_date(t.get("due_date")) < today)
            # Stored + mailed text: compose it in the recipient's language.
            with use_language(await language_of(user)):
                subject = ngettext(
                    "Reminder: %(count)d task with a due date",
                    "Reminder: %(count)d tasks with a due date",
                    len(items),
                ) % {"count": len(items)}
                if overdue:
                    subject += " (" + _("%(count)s overdue") % {"count": overdue} + ")"
                message = "\n".join(_line(t, titles, today) for t in _sorted(items))
            try:
                await notification_service.notify(
                    session,
                    user=user,
                    doctype="ToDo",
                    doc_id=items[0]["name"],
                    subject=subject,
                    message=message,
                    email=True,
                )
            except Exception:
                log.exception("todo_reminders.notify_failed", user=user)

        await session.commit()
        log.info("todo_reminders.sent", users=len(by_user), tasks=len(todos))


def _as_date(value: Any) -> date:
    """Coerce a stored due_date (date | ISO string | None) to a ``date``."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.max


def _sorted(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda t: _as_date(t.get("due_date")))


def _line(t: dict[str, Any], titles: dict[tuple[str, str], str], today: date) -> str:
    ref = titles.get((t.get("reference_doctype") or "", t.get("reference_id") or "")) or (
        t.get("reference_id") or ""
    )
    due = _as_date(t.get("due_date"))
    mark = "⚠ " + _("overdue") if due < today else _("today")
    note = (t.get("description") or "").strip() or ref or t["name"]
    return f"• [{due.isoformat()}, {mark}] {note}"
