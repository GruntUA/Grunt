"""NotificationService — evaluates notification rules and creates notifications.

Integrates with the hook system: after_save, after_insert, on_transition events
trigger rule evaluation. Matching rules create system notifications and optionally
queue emails.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class NotificationService:
    """Evaluates notification rules and creates notifications for users."""

    async def evaluate_rules(
        self,
        session: AsyncSession,
        event: str,
        doctype: str,
        doc: dict[str, Any],
        user_email: str,
    ) -> int:
        """Evaluate all matching notification rules for a document event.

        Args:
            session: DB session.
            event: Event type (after_insert, after_save, on_transition, etc.).
            doctype: DocType name.
            doc: Document data.
            user_email: Email of the user who triggered the event.

        Returns:
            Number of notifications created.
        """
        from grunt.core.db.system_tables import GruntNotificationRule  # noqa: PLC0415

        stmt = (
            select(GruntNotificationRule)
            .where(GruntNotificationRule.doctype == doctype)
            .where(GruntNotificationRule.event == event)
            .where(GruntNotificationRule.is_enabled.is_(True))
        )
        result = await session.execute(stmt)
        rules = result.scalars().all()

        count = 0
        for rule in rules:
            # Check condition
            if rule.condition and not self._eval_condition(rule.condition, doc, user_email):
                continue

            # Resolve recipients
            recipients = self._resolve_recipients(rule.recipients, doc, user_email)
            if not recipients:
                continue

            # Format subject and message
            subject = self._format_template(rule.subject_template, doctype, doc, event)
            message = self._format_template(rule.message_template, doctype, doc, event)

            # Create notifications
            for recipient in recipients:
                await self._create_notification(
                    session=session,
                    user=recipient,
                    doctype=doctype,
                    doc_id=str(doc.get("id", "")),
                    subject=subject,
                    message=message,
                )
                count += 1

                # Send email if channel includes email
                if rule.channel in ("email", "both"):
                    await self._queue_email(session, recipient, subject, message)

            # Broadcast via WebSocket if channel includes system
            if rule.channel in ("system", "both"):
                await self._broadcast_ws(doctype, doc, subject, recipients)

        if count > 0:
            await session.flush()
            logger.info(
                "notification.sent",
                event=event,
                doctype=doctype,
                doc_id=doc.get("id"),
                count=count,
            )

        return count

    async def get_notifications(
        self,
        session: AsyncSession,
        user: str,
        unread_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get notifications for a user."""
        from grunt.core.db.system_tables import GruntNotification  # noqa: PLC0415

        stmt = (
            select(GruntNotification)
            .where(GruntNotification.user == user)
            .order_by(GruntNotification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if unread_only:
            stmt = stmt.where(GruntNotification.is_read.is_(False))

        result = await session.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "id": row.id,
                "subject": row.subject,
                "message": row.message,
                "doctype": row.doctype,
                "doc_id": row.doc_id,
                "is_read": row.is_read,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    async def mark_read(self, session: AsyncSession, notification_id: str) -> None:
        """Mark a single notification as read."""
        from grunt.core.db.system_tables import GruntNotification  # noqa: PLC0415

        await session.execute(
            update(GruntNotification)
            .where(GruntNotification.id == notification_id)
            .values(is_read=True)
        )
        await session.flush()

    async def mark_all_read(self, session: AsyncSession, user: str) -> int:
        """Mark all notifications as read for a user. Returns count of affected."""
        from grunt.core.db.system_tables import GruntNotification  # noqa: PLC0415

        result = await session.execute(
            update(GruntNotification)
            .where(GruntNotification.user == user)
            .where(GruntNotification.is_read.is_(False))
            .values(is_read=True)
        )
        await session.flush()
        return result.rowcount  # type: ignore[return-value]

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _create_notification(
        self,
        session: AsyncSession,
        user: str,
        doctype: str,
        doc_id: str,
        subject: str,
        message: str,
    ) -> str:
        from grunt.core.db.system_tables import GruntNotification  # noqa: PLC0415

        notif_id = str(uuid.uuid4())
        notif = GruntNotification(
            id=notif_id,
            user=user,
            doctype=doctype,
            doc_id=doc_id,
            subject=subject,
            message=message,
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        session.add(notif)
        return notif_id

    def _resolve_recipients(
        self,
        recipients_str: str,
        doc: dict[str, Any],
        triggering_user: str,
    ) -> list[str]:
        """Parse recipient spec into list of email addresses.

        Supports:
          - "owner"           → doc owner
          - "role:Manager"    → all users with this role (TODO: query users table)
          - "user@example.com" → literal email
          - "{field:assigned_to}" → value of a field
        """
        if not recipients_str:
            return []

        results: set[str] = set()
        for part in recipients_str.split(","):
            part = part.strip()
            if not part:
                continue

            if part == "owner":
                owner = doc.get("owner")
                if owner:
                    results.add(owner)
            elif part.startswith("role:"):
                # TODO: query GruntUser by role — for now skip
                pass
            elif part.startswith("{field:") and part.endswith("}"):
                field_name = part[7:-1]
                value = doc.get(field_name)
                if value and isinstance(value, str):
                    results.add(value)
            elif "@" in part:
                results.add(part)

        # Don't notify the user who triggered the event
        results.discard(triggering_user)
        return list(results)

    def _format_template(
        self,
        template: str,
        doctype: str,
        doc: dict[str, Any],
        event: str,
    ) -> str:
        """Simple template formatting with {key} placeholders."""
        context = {
            "doctype": doctype,
            "event": event,
            "name": doc.get("name", ""),
            "id": doc.get("id", ""),
            "owner": doc.get("owner", ""),
        }
        # Add all doc fields
        for k, v in doc.items():
            if k not in context:
                context[k] = str(v) if v is not None else ""

        try:
            return template.format(**context)
        except (KeyError, IndexError):
            return template

    def _eval_condition(self, condition: str, doc: dict[str, Any], user: str) -> bool:
        """Evaluate a Python condition expression safely."""
        safe_globals: dict = {"__builtins__": {}}
        safe_locals: dict = {"doc": doc, "user": user}
        try:
            return bool(eval(condition, safe_globals, safe_locals))  # noqa: S307
        except Exception:  # noqa: BLE001
            return True  # Don't block on eval errors

    async def _queue_email(
        self,
        session: AsyncSession,
        recipient: str,
        subject: str,
        message: str,
    ) -> None:
        """Queue an email notification via the existing email system."""
        try:
            from grunt.core.email.service import email_service  # noqa: PLC0415

            await email_service.queue_email(
                session=session,
                to=recipient,
                subject=subject,
                body=message,
            )
        except Exception:  # noqa: BLE001
            logger.warning("notification.email_queue_error", recipient=recipient)

    async def _broadcast_ws(
        self,
        doctype: str,
        doc: dict[str, Any],
        subject: str,
        recipients: list[str],
    ) -> None:
        """Send WebSocket notification to connected users."""
        try:
            from grunt.api.v1.ws import manager  # noqa: PLC0415

            for recipient in recipients:
                await manager.send_to_user(
                    recipient,
                    {
                        "event": "notification",
                        "data": {
                            "subject": subject,
                            "doctype": doctype,
                            "doc_id": str(doc.get("id", "")),
                        },
                    },
                )
        except Exception:  # noqa: BLE001
            pass  # WS broadcast is best-effort
