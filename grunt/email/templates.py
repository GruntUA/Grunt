"""EmailTemplate rendering — queue transactional email without hardcoding
subject/body strings in app controllers.

Placeholders use plain ``str.format()`` syntax against the caller's context
dict — the same convention ``grunt.notification.service`` already uses for
NotificationRule templates — rather than reaching for a templating engine for
what is normally a handful of substitutions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class EmailTemplateError(Exception):
    """Raised when a named EmailTemplate doesn't exist or is inactive."""


def _format(template: str, context: dict[str, Any]) -> str:
    try:
        return template.format(**context)
    except (KeyError, IndexError):
        return template


async def render(name: str, context: dict[str, Any]) -> tuple[str, str, str | None]:
    """Return ``(subject, body_text, body_html)`` for EmailTemplate *name*.

    Runs under ``system_context`` — EmailTemplate is System-Manager-only to
    edit, but any server-side code path needs to be able to render one,
    including one acting as a synthetic Guest (e.g. a public WebForm
    submission queuing its own confirmation e-mail).
    """
    from grunt.app import grunt
    from grunt.context import require_session

    async with grunt.system_context(require_session()):
        rows = await grunt.db.get_all(
            "EmailTemplate",
            filters={"name": name, "is_active": True},
            fields=["subject", "body", "body_html"],
            limit=1,
        )

    if not rows:
        raise EmailTemplateError(f"Email-шаблон «{name}» не знайдено або вимкнено")

    row = rows[0]
    subject = _format(row["subject"], context)
    body_text = _format(row["body"], context)
    body_html = _format(row["body_html"], context) if row.get("body_html") else None
    return subject, body_text, body_html


async def queue(session: AsyncSession, *, to: str, name: str, context: dict[str, Any]) -> str:
    """Render EmailTemplate *name* against *context* and queue it in one call."""
    from grunt.email.service import email_service

    subject, body_text, body_html = await render(name, context)
    return await email_service.queue_email(
        session=session, to=to, subject=subject, body=body_text, html_body=body_html
    )
