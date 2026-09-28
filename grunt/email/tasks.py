from __future__ import annotations

from datetime import UTC, datetime, timedelta

from grunt.app import grunt
from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.email.service import EmailService, decode_attachments, email_service
from grunt.log import log
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task


@retryable_task()
async def process_email_queue():
    """Select Pending emails from EmailQueue and send them."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session, grunt.system_context(session, eng):
        try:
            # Reopen rows a crashed run left mid-flight (claimed "Sending" but
            # never marked Sent/Error) so they get retried, not stranded.
            reopened = await grunt.db.bulk_update(
                "EmailQueue",
                {
                    "status": "Sending",
                    "modified_at__lt": datetime.now(UTC) - timedelta(minutes=10),
                },
                {"status": "Pending"},
            )
            if reopened:
                await session.commit()
                log.warning("email.queue_reopened_stale", count=reopened)

            queue_items = await grunt.get_list(
                "EmailQueue", filters={"status": "Pending"}, limit=100
            )

            if not queue_items:
                return

            log.info("email.processing_queue", count=len(queue_items))

            for item in queue_items:
                account_id = item.get("email_account")
                if not account_id:
                    log.warning("email.no_account_for_item", id=item["name"])
                    continue

                # Atomically claim the row: flip Pending → Sending and bail if a
                # concurrent run (on-commit kick overlapping the */5 cron tick)
                # already took it. Without this both runs would send the mail.
                claimed = await grunt.db.bulk_update(
                    "EmailQueue",
                    {"name": item["name"], "status": "Pending"},
                    {"status": "Sending", "modified_at": datetime.now(UTC)},
                )
                await session.commit()
                if not claimed:
                    continue

                account = await grunt.get_doc("EmailAccount", account_id)
                await session.commit()  # no transaction (write lock) across SMTP

                try:
                    message = {**item, "attachments": decode_attachments(item.get("attachments"))}
                    await EmailService.send_now(account, message)
                    await grunt.save_doc("EmailQueue", item["name"], {"status": "Sent"})
                    await session.commit()
                except Exception as e:
                    await grunt.save_doc(
                        "EmailQueue",
                        item["name"],
                        {"status": "Error", "error_message": str(e)},
                    )
                    await session.commit()

        except Exception as e:
            log.error("email.queue_processing_failed", error=str(e))
            raise


@retryable_task()
async def pull_from_accounts():
    """Fetch emails from all active EmailAccounts."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session, grunt.system_context(session, eng):
        try:
            accounts = await grunt.get_list(
                "EmailAccount", filters={"enable_incoming": "True"}, limit=1000
            )
            await session.commit()  # no transaction (write lock) across IMAP

            for account in accounts:
                emails = await EmailService.pull_emails(account)
                for email_data in emails:
                    # Trigger hook for inbound email
                    # Apps can register to this hook to create Support Tickets, Leads, etc.
                    from grunt.events import fire

                    await fire(
                        "inbound_email",
                        account=account,
                        email_data=email_data,
                        session=session,
                        user=SYSTEM_USER,
                    )

                    # Delivery-status (DSN) / read-receipt (MDN) report —
                    # update the referenced outgoing message, don't file it as
                    # a normal inbound letter.
                    report = email_data.get("report")
                    if report:
                        try:
                            await EmailService.apply_report(report, session=session)
                        except Exception:
                            log.exception("email.apply_report_failed")
                        await session.commit()
                        continue

                    # Persist to the mailbox (EmailMessage).
                    try:
                        att_rows = []
                        for att in email_data.get("attachments") or []:
                            url = await EmailService.store_bytes(
                                att.get("content") or b"",
                                att.get("filename") or "attachment",
                                att.get("mimetype"),
                            )
                            att_rows.append(
                                {
                                    "file": url,
                                    "filename": att.get("filename") or "attachment",
                                    "size": len(att.get("content") or b""),
                                    "mimetype": att.get("mimetype") or "",
                                }
                            )
                        await EmailService.record_message(
                            direction="Incoming",
                            status="Received",
                            subject=email_data.get("subject", ""),
                            sender=email_data.get("sender", ""),
                            recipients=email_data.get("recipients", ""),
                            cc=email_data.get("cc") or None,
                            email_account=account.get("name"),
                            body_html=email_data.get("html") or None,
                            body_text=email_data.get("text") or None,
                            message_date=EmailService.parse_date(email_data.get("date")),
                            message_id=email_data.get("message_id"),
                            attachments=att_rows,
                            session=session,
                        )
                    except Exception:
                        log.exception("email.record_inbound_failed")

                    await session.commit()

        except Exception as e:
            log.error("email.pull_from_accounts_failed", error=str(e))
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

    hours = 24 if period == "daily" else 168
    since = datetime.now(UTC) - timedelta(hours=hours)
    period_label = "за останню добу" if period == "daily" else "за останній тиждень"
    period_subj = "Щоденний" if period == "daily" else "Тижневий"

    async with maker() as session:
        from grunt.app import grunt

        sent = 0
        async with grunt.system_context(session):
            user_rows = await grunt.db.get_all(
                "User",
                filters={"is_active": True},
                fields=["email"],
                limit=10_000,
            )
            users = [r["email"] for r in user_rows if r.get("email")]

            for user_email in users:
                # Fetch unread notifications for this user since cutoff
                rows = await grunt.db.get_all(
                    "Notification",
                    filters={
                        "user": user_email,
                        "is_read": False,
                        "created_at__gte": since,
                    },
                    order_by="created_at",
                    order="desc",
                    limit=500,
                )
                if not rows:
                    continue

                # Group by doctype
                groups: dict[str, list] = {}
                for n in rows:
                    key = str(n.get("doctype") or "Система")
                    groups.setdefault(key, []).append(n)

                subject = f"{period_subj} дайджест: {len(rows)} нових сповіщень"

                html_body = await grunt.render_template(
                    "notification_digest.html",
                    {
                        "period_subj": period_subj,
                        "period_label": period_label,
                        "total": len(rows),
                        "groups": groups,
                    },
                )

                try:
                    await email_service.queue_email(
                        session=session,
                        to=user_email,
                        subject=subject,
                        body=subject,
                        html_body=html_body,
                    )
                    sent += 1
                except Exception:
                    log.warning("digest.email_queue_failed", user=user_email)

        await session.commit()
        log.info("digest.sent", period=period, users=sent)
