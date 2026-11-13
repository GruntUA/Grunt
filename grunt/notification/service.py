"""NotificationService - evaluates notification rules and creates notifications.

Integrates with the hook system: after_save, after_insert, on_transition events
trigger rule evaluation. Matching rules hand their message to the dispatcher
(:func:`grunt.notification.delivery.deliver`), which sends it through the
rule's channels and logs each delivery.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.db.api import GruntDB
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.notification import rules
from grunt.notification.channels import Message
from grunt.notification.delivery import deliver
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session


class NotificationService:
    """Evaluates notification rules and creates notifications for users."""

    async def evaluate_rules(
        self,
        session: AsyncSession,
        event: str,
        doctype: str,
        doc: dict[str, Any],
        user_email: str,
        extra: dict[str, Any] | None = None,
    ) -> int:
        """Evaluate all matching notification rules for a document event.

        Args:
            session: DB session.
            event: Event type (after_insert, after_save, on_transition, etc.).
            doctype: DocType name.
            doc: Document data.
            user_email: Email of the user who triggered the event.
            extra: More template variables - for ``on_transition``: ``action``,
                ``from_state``, ``to_state``, ``comment``.

        Returns:
            Number of notifications created.
        """
        async with system_context(session):
            rules = await _db.get_all(
                "Notification",
                filters={"ref_doctype": doctype, "event": event, "is_enabled": True},
                limit=100,
            )

        count = 0
        for rule in rules:
            count += await self.apply_rule(
                session, rule, doctype, doc, user_email, event, extra=extra
            )

        if count > 0:
            await session.flush()
            log.info(
                "notification.sent",
                doc_event=event,
                doctype=doctype,
                doc_id=doc.get("name"),
                count=count,
            )

        return count

    async def apply_rule(
        self,
        session: AsyncSession,
        rule: dict[str, Any],
        doctype: str,
        doc: dict[str, Any],
        user_email: str,
        event: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> int:
        """Run one rule against one document: condition, recipients, delivery.

        Returns the number of recipients notified.
        """
        return await rules.run(
            session, rule, doctype, doc, actor=user_email, event=event, extra=extra
        )

    async def get_notifications(
        self,
        user: str,
        unread_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get notifications for a user."""

        filters: dict[str, Any] = {"user": user}
        if unread_only:
            filters["is_read"] = False

        async with system_context(require_session()):
            rows = await _db.get_all(
                "NotificationLog",
                filters=filters,
                fields=[
                    "name",
                    "subject",
                    "message",
                    "ref_doctype",
                    "doc_id",
                    "is_read",
                    "created_at",
                ],
                limit=limit,
                offset=offset,
                order_by="created_at",
                order="desc",
            )

        return [
            {
                **row,
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
            for row in rows
        ]

    async def mark_read(self, notification_id: str) -> None:
        """Mark a single notification as read."""

        async with system_context(require_session()):
            await _db.set_value("NotificationLog", notification_id, "is_read", True)

    async def mark_all_read(self, user: str) -> int:
        """Mark all notifications as read for a user. Returns count of affected."""

        async with system_context(require_session()):
            return await documents.bulk_update(
                "NotificationLog",
                {"user": user, "is_read": False},
                {"is_read": True},
            )

    async def notify(
        self,
        session: AsyncSession,
        *,
        user: str,
        doctype: str,
        doc_id: str,
        subject: str,
        message: str,
        email: bool = False,
        url: str | None = None,
    ) -> str | None:
        """Deliver one notification to *user* directly (bypasses the rules).

        In the system + browser push always; ``email`` also queues a mail.
        For code paths that must ping a specific person - e.g. document
        assignment - without a configurable rule in the loop. Returns the
        ``NotificationLog`` (bell) row's name.
        """
        if not user:
            return None
        channels = ["in_app", "web_push"] + (["email"] if email else [])
        report = await deliver(
            session,
            [user],
            Message(subject=subject, body=message, url=url, ref_doctype=doctype, doc_id=doc_id),
            channels,
        )
        return report.notification_logs[0] if report.notification_logs else None

    # Internal helpers

    def _resolve_recipients(
        self,
        recipients_str: str,
        doc: dict[str, Any],
        triggering_user: str,
    ) -> tuple[list[str], list[str]]:
        """Parse recipient spec into (emails, role names still needing async lookup).

        Supports:
          - "owner"            -> doc owner
          - "role:Manager"     -> all active users with this role (resolved by the
                                  caller via _resolve_role_recipients - needs a DB
                                  round-trip, so it can't happen inside this
                                  synchronous parse)
          - "user@example.com" -> literal email
          - "{field:fieldname}" -> value of a doc field
        """
        if not recipients_str:
            return [], []

        results: set[str] = set()
        role_parts: list[str] = []

        for part in recipients_str.split(","):
            part = part.strip()
            if not part:
                continue

            if part == "owner":
                owner = doc.get("owner")
                if owner:
                    results.add(owner)
            elif part.startswith("role:"):
                role_parts.append(part[5:])
            elif part.startswith("{field:") and part.endswith("}"):
                field_name = part[7:-1]
                value = doc.get(field_name)
                if value and isinstance(value, str):
                    results.add(value)
            elif "@" in part:
                results.add(part)

        # Don't notify the user who triggered the event
        results.discard(triggering_user)
        return list(results), role_parts

    async def _resolve_role_recipients(
        self,
        role_names: list[str],
        session: AsyncSession,
    ) -> list[str]:
        """Return email addresses of all active users with any of the given roles."""
        if not role_names:
            return []
        try:
            async with system_context(session):
                # Collect user_ids for all requested roles
                user_ids: set[str] = set()
                for role in role_names:
                    rows = await _db.get_all(
                        "UserRole",
                        filters={"role_name": role, "parent_doctype": "User"},
                        fields=["parent_name"],
                        limit=1000,
                    )
                    user_ids.update(r["parent_name"] for r in rows)

                if not user_ids:
                    return []

                # Resolve to emails - only active users
                emails: list[str] = []
                for user_id in user_ids:
                    user_rows = await _db.get_all(
                        "User",
                        filters={"name": user_id, "is_active": True},
                        fields=["email"],
                        limit=1,
                    )
                    if user_rows and user_rows[0].get("email"):
                        emails.append(user_rows[0]["email"])
                return emails
        except Exception:
            log.warning("notification.role_resolution_failed", roles=role_names)
            return []


notification_service = NotificationService()
