from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from grunt.core.tasks.broker import retryable_task
from grunt.core.email.service import EmailService, email_service
from grunt.core.site.manager import site_manager

from grunt.core.document.service import DocumentService
from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()

# System user for email tasks
SYSTEM_USER = GruntUser(
    email="system@grunt.local",
    full_name="System",
    is_superadmin=True
)

@retryable_task()
async def process_email_queue():
    """Select Pending emails from EmailQueue and send them."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session:
        service = DocumentService(session, eng)
        
        # 1. Fetch Pending emails
        try:
            result = await service.list_documents(
                "EmailQueue", 
                SYSTEM_USER, 
                filters={"status": "Pending"},
                per_page=100
            )
            queue_items = result["data"]
            
            if not queue_items:
                return

            logger.info("email.processing_queue", count=len(queue_items))

            for item in queue_items:
                # 2. Get Account settings
                # Note: list_documents returns raw data. We need to fetch the account.
                account_id = item.get("email_account")
                if not account_id:
                    logger.warning("email.no_account_for_item", id=item["id"])
                    continue
                
                account = await service.get_document("EmailAccount", account_id, SYSTEM_USER)
                
                try:
                    # 3. Send
                    await EmailService.send_now(account, item)
                    
                    # 4. Update status
                    await service.update_document(
                        "EmailQueue", 
                        item["id"], 
                        {"status": "Sent"}, 
                        SYSTEM_USER
                    )
                    await session.commit()
                except Exception as e:
                    await service.update_document(
                        "EmailQueue", 
                        item["id"], 
                        {"status": "Error", "error_message": str(e)}, 
                        SYSTEM_USER
                    )
                    await session.commit()
                    
        except Exception as e:
            logger.error("email.queue_processing_failed", error=str(e))
            raise


@retryable_task()
async def pull_from_accounts():
    """Fetch emails from all active EmailAccounts."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session:
        service = DocumentService(session, eng)
        
        try:
            result = await service.list_documents(
                "EmailAccount", 
                SYSTEM_USER, 
                filters={"enable_incoming": "True"}
            )
            accounts = result["data"]
            
            for account in accounts:
                emails = await EmailService.pull_emails(account)
                for email_data in emails:
                    # Trigger hook for inbound email
                    # Apps can register to this hook to create Support Tickets, Leads, etc.
                    from grunt.core.hooks import fire
                    await fire(
                        "inbound_email", 
                        account=account, 
                        email_data=email_data,
                        session=session,
                        user=SYSTEM_USER
                    )
                    await session.commit()
                    
        except Exception as e:
            logger.error("email.pull_from_accounts_failed", error=str(e))
            raise


@retryable_task()
async def send_notification_digest(period: str = "daily") -> None:
    """Send unread-notification digest emails to all active users.

    ``period`` must be ``"daily"`` or ``"weekly"``.
    Collects unread notifications from the last 24h (daily) or 7d (weekly),
    groups them by DocType, and sends one email per user who has unread items.
    """
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)

    hours = 24 if period == "daily" else 168
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    period_label = "за останню добу" if period == "daily" else "за останній тиждень"

    async with maker() as session:
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.auth.service import _user_table  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        notif_dt = doctype_registry._doctypes.get("Notification")
        if not notif_dt:
            return
        notif_table = compile_doctype_to_table(notif_dt)

        # Load all active users with an email
        user_table = _user_table()
        user_rows = (await session.execute(
            select(user_table.c.email).where(user_table.c.is_active.is_(True))
        )).all()
        users = [r[0] for r in user_rows if r[0]]

        sent = 0
        for user_email in users:
            # Fetch unread notifications for this user since cutoff
            stmt = (
                select(notif_table)
                .where(notif_table.c.user == user_email)
                .where(notif_table.c.is_read.is_(False))
                .where(notif_table.c.created_at >= since)
                .order_by(notif_table.c.created_at.desc())
            )
            rows = (await session.execute(stmt)).mappings().all()
            if not rows:
                continue

            # Group by doctype
            groups: dict[str, list] = {}
            for n in rows:
                key = str(n.get("doctype") or "Система")
                groups.setdefault(key, []).append(n)

            # Build HTML digest
            html_parts = [
                "<h2>Дайджест сповіщень Ґрунт</h2>",
                f"<p>Непрочитані сповіщення {period_label}:</p>",
            ]
            for doctype_key, items in groups.items():
                html_parts.append(f"<h3>{doctype_key} ({len(items)})</h3><ul>")
                for item in items[:10]:  # max 10 per group
                    subject = item.get("subject", "")
                    created = item.get("created_at")
                    ts = created.strftime("%d.%m %H:%M") if created else ""
                    html_parts.append(f"<li><b>{subject}</b> <small>{ts}</small></li>")
                if len(items) > 10:
                    html_parts.append(f"<li>… і ще {len(items) - 10}</li>")
                html_parts.append("</ul>")

            html_body = "\n".join(html_parts)
            period_subj = "Щоденний" if period == "daily" else "Тижневий"
            subject = f"{period_subj} дайджест: {len(rows)} нових сповіщень"

            try:
                await email_service.queue_email(
                    session=session,
                    to=user_email,
                    subject=subject,
                    body=subject,
                    html_body=html_body,
                )
                sent += 1
            except Exception:  # noqa: BLE001
                logger.warning("digest.email_queue_failed", user=user_email)

        await session.commit()
        logger.info("digest.sent", period=period, users=sent)
