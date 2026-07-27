from __future__ import annotations

import asyncio
from typing import Any

import structlog

from grunt.db.session import async_session_factory
from grunt.notification.service import notification_service
from grunt.tasks.broker import task

logger = structlog.get_logger()


@task
async def evaluate_notification_rules_task(
    event: str,
    doctype: str,
    doc: dict[str, Any],
    user_email: str,
) -> None:
    """Background task to evaluate notification rules.

    Creates its own database session to avoid sharing with the main request.
    """
    try:
        async with async_session_factory() as session:
            await notification_service.evaluate_rules(
                session=session,
                event=event,
                doctype=doctype,
                doc=doc,
                user_email=user_email,
            )
            await session.commit()
    except asyncio.CancelledError:
        logger.debug("notification.task_cancelled", trigger_event=event, doctype=doctype)
    except Exception:
        logger.error("notification.task_error", exc_info=True, trigger_event=event, doctype=doctype)
