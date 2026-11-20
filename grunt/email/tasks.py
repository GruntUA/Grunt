from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.auth.constants import SYSTEM_USER_EMAIL
from grunt.db.api import GruntDB
from grunt.email.inbound import apply_report, pull_emails
from grunt.email.routing import file_inbound
from grunt.email.service import (
    PRIORITIES,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    RETRY_DELAYS_MINUTES,
    EmailService,
    decode_attachments,
    email_service,
    is_temporary,
)
from grunt.email.unsubscribe import footer as unsubscribe_footer
from grunt.email.unsubscribe import is_unsubscribed, unsubscribe_url
from grunt.i18n import _, ngettext, pgettext, use_language
from grunt.local import system_context
from grunt.log import log
from grunt.notification import delivery_log
from grunt.permissions.groups import group_emails
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task
from grunt.utils.templates import render as render_template_text
lazy from grunt.document.api import documents
lazy from grunt.events import fire
lazy from grunt.notification.service import notification_service

_db = GruntDB()  # stateless: reads through the context's session


async def due_emails(limit: int) -> list[dict]:
    """Pending letters whose time has come, higher priority first, older first
    within one level (an empty priority - a row queued before priorities -
    goes with ``Normal``)."""
    now = datetime.now(UTC)
    rows: list[dict] = []
    for level in PRIORITIES:
        if len(rows) >= limit:
            break
        where: dict = {"status": "Pending", "send_after__lte_or_null": now}
        levels: dict = {"priority": level}
        if level == PRIORITY_NORMAL:
            levels["priority__isnull"] = True
        rows += await _db.get_all(
            "EmailQueue",
            filters=where,
            or_filters=levels,
            fields=["*"],
            order_by="created_at",
            order="asc",
            limit=limit - len(rows),
        )
    return rows


@retryable_task()
async def process_email_queue():
    """Select Pending emails from EmailQueue and send them."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session, system_context(session, eng):
        try:
            # Reopen rows a crashed run left mid-flight (claimed "Sending" but
            # never marked Sent/Error) so they get retried, not stranded.
            reopened = await _db.bulk_update(
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

            queue_items = await due_emails(limit=100)

            if not queue_items:
                return

            log.info("email.processing_queue", count=len(queue_items))

            for item in queue_items:
                account_id = item.get("email_account")
                if not account_id:
                    log.warning("email.no_account_for_item", id=item["name"])
                    continue

                # Atomically claim the row: flip Pending -> Sending and bail if a
                # concurrent run (on-commit kick overlapping the */5 cron tick)
                # already took it. Without this both runs would send the mail.
                claimed = await _db.bulk_update(
                    "EmailQueue",
                    {"name": item["name"], "status": "Pending"},
                    {"status": "Sending", "modified_at": datetime.now(UTC)},
                )
                await session.commit()
                if not claimed:
                    continue

                account = await documents.get_doc("EmailAccount", account_id)
                await session.commit()  # no transaction (write lock) across SMTP

                try:
                    message = {**item, "attachments": decode_attachments(item.get("attachments"))}
                    email_message = await EmailService.send_now(account, message)
                    await documents.save_doc("EmailQueue", item["name"], {"status": "Sent"})
                    await delivery_log.settle(
                        {"email_queue": item["name"]}, "Sent", email_message=email_message
                    )
                    await session.commit()
                except Exception as e:
                    attempt = int(item.get("retry") or 0)
                    if is_temporary(e) and attempt < len(RETRY_DELAYS_MINUTES):
                        # Try again later; the delivery stays "Queued".
                        pause = timedelta(minutes=RETRY_DELAYS_MINUTES[attempt])
                        await documents.save_doc(
                            "EmailQueue",
                            item["name"],
                            {
                                "status": "Pending",
                                "retry": attempt + 1,
                                "send_after": datetime.now(UTC) + pause,
                                "error_message": str(e),
                            },
                        )
                        log.info("email.send_retry", id=item["name"], attempt=attempt + 1)
                    else:
                        await documents.save_doc(
                            "EmailQueue",
                            item["name"],
                            {"status": "Error", "error_message": str(e)},
                        )
                        await delivery_log.settle(
                            {"email_queue": item["name"]}, "Error", reason=str(e)
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
    async with maker() as session, system_context(session, eng):
        try:
            accounts = await documents.get_list(
                "EmailAccount", filters={"enable_incoming": "True"}, limit=1000
            )
            await session.commit()  # no transaction (write lock) across IMAP

            for account in accounts:
                emails, imap_state = await pull_emails(account)
                for email_data in emails:
                    await _file_one(session, account, email_data)
                # Where this run stopped - saved after the letters are filed,
                # so a crash re-reads them (Message-ID dedup keeps them single).
                await _db.set_value("EmailAccount", account["name"], "imap_state", imap_state)
                await session.commit()

        except Exception as e:
            log.error("email.pull_from_accounts_failed", error=str(e))
            raise


async def _file_one(session: AsyncSession, account: dict, email_data: dict) -> None:
    """One pulled letter: a delivery/read report updates the letter it is
    about; anything else is filed (``grunt.email.routing``), then the
    ``inbound_email`` event lets apps react."""
    report = email_data.get("report")
    if report:
        try:
            await apply_report(report, session=session)
        except Exception:
            log.exception("email.apply_report_failed")
        await session.commit()
        return

    filed = None
    try:
        filed = await file_inbound(session, account, email_data)
    except Exception:
        log.exception("email.record_inbound_failed")
    await session.commit()
    if filed is None:
        return  # already filed by an earlier run, or failed
    try:
        await fire(
            "inbound_email",
            account=account,
            email_data=email_data,
            filed=filed,
            session=session,
            user=SYSTEM_USER_EMAIL,
        )
        await session.commit()
    except Exception:
        log.exception("email.inbound_hook_failed")
        await session.rollback()


# The unanswered-letter check looks back this far beyond the account's minutes.
UNREPLIED_LOOKBACK = timedelta(days=1)


async def unreplied_recipients(account: dict, doctype: str, name: str) -> list[str]:
    """Who hears of an unanswered letter: the document's assignees, else the
    mailbox's group."""
    rows = await _db.get_all(
        "ToDo",
        filters={
            "reference_doctype": doctype,
            "reference_id": name,
            "status__in": ["Open", "In Progress"],
        },
        fields=["assigned_to"],
        limit=None,
    )
    people = sorted({r["assigned_to"] for r in rows if r.get("assigned_to")})
    if not people and account.get("unreplied_group"):
        people = sorted(set(await group_emails([account["unreplied_group"]])))
    return people


async def process_unreplied(session: AsyncSession, now: datetime | None = None) -> int:
    """Notify about letters on documents left unanswered past the mailbox's
    ``unreplied_minutes``; runs inside a system context. Each letter is checked
    once (``unreplied_checked``); only the last letter of a document counts,
    and an auto-reply is no answer. Returns the notifications sent."""
    now = now or datetime.now(UTC)
    accounts = await _db.get_all("EmailAccount", filters={"notify_if_unreplied": True}, limit=None)
    sent = 0
    for account in accounts:
        due = now - timedelta(minutes=max(1, int(account.get("unreplied_minutes") or 30)))
        rows = await _db.get_all(
            "EmailMessage",
            filters={
                "direction": "Incoming",
                "email_account": account["name"],
                "unreplied_checked": False,
                "ref_doctype__is": "set",
                "created_at__lte": due,
                "created_at__gte": due - UNREPLIED_LOOKBACK,
            },
            fields=["name", "ref_doctype", "ref_name", "subject", "sender", "created_at"],
            order_by="created_at",
            order="asc",
            limit=500,
        )
        for row in rows:
            doctype, name = str(row["ref_doctype"]), str(row["ref_name"] or "")
            later = {
                "ref_doctype": doctype,
                "ref_name": name,
                "created_at__gt": row["created_at"],
            }
            newer = await _db.exists("EmailMessage", {**later, "direction": "Incoming"})
            answered = await _db.exists(
                "EmailMessage",
                {**later, "direction": "Outgoing", "is_auto_reply": False, "status__ne": "Error"},
            )
            if not newer and not answered and name and await _db.exists(doctype, name):
                for user in await unreplied_recipients(account, doctype, name):
                    await notification_service.notify(
                        session,
                        user=user,
                        doctype=doctype,
                        doc_id=name,
                        subject=_("No reply to a letter: %(doctype)s %(name)s")
                        % {"doctype": _(doctype), "name": name},
                        message=_("%(sender)s: %(subject)s")
                        % {"sender": row.get("sender") or "", "subject": row.get("subject") or ""},
                        email=True,
                    )
                    sent += 1
            await _db.set_value("EmailMessage", row["name"], "unreplied_checked", True)
    return sent


@retryable_task()
async def check_unreplied() -> None:
    """Scheduler: letters left unanswered (EmailAccount.notify_if_unreplied)."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, system_context(session):
        sent = await process_unreplied(session)
        await session.commit()
        if sent:
            log.info("email.unreplied_notified", count=sent)


async def _render_digest(period: str, rows: list[dict], groups: dict[str, list]) -> tuple[str, str]:
    """Subject + HTML body of one digest, in the current (recipient's) language."""
    total = len(rows)
    if period == "daily":
        title = _("Daily notification digest")
        summary = ngettext(
            "%(count)d unread notification in the last day",
            "%(count)d unread notifications in the last day",
            total,
        )
    else:
        title = _("Weekly notification digest")
        summary = ngettext(
            "%(count)d unread notification in the last week",
            "%(count)d unread notifications in the last week",
            total,
        )
    summary %= {"count": total}
    labelled = {
        (pgettext(f"meta:{key}", key) if key else _("System")): items
        for key, items in groups.items()
    }
    html_body = await render_template_text(
        "notification_digest.html",
        {"title": title, "summary": summary, "total": total, "groups": labelled},
    )
    return f"{title}: {summary}", html_body


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

    async with maker() as session:
        sent = 0
        async with system_context(session):
            user_rows = await _db.get_all(
                "User",
                filters={"is_active": True},
                fields=["email", "language"],
                limit=10_000,
            )
            users = [(r["email"], r.get("language")) for r in user_rows if r.get("email")]

            for user_email, user_language in users:
                if await is_unsubscribed(user_email):
                    continue
                # Fetch unread notifications for this user since cutoff
                rows = await _db.get_all(
                    "NotificationLog",
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
                    key = str(n.get("ref_doctype") or "")
                    groups.setdefault(key, []).append(n)

                with use_language(user_language):
                    subject, html_body = await _render_digest(period, rows, groups)

                link = unsubscribe_url(user_email)
                html_line, text_line = unsubscribe_footer(link)
                try:
                    await email_service.queue_email(
                        session=session,
                        to=user_email,
                        subject=subject,
                        body=f"{subject}\n\n{text_line}",
                        html_body=html_body + html_line,
                        priority=PRIORITY_LOW,
                        unsubscribe_url=link,
                    )
                    sent += 1
                except Exception:
                    log.warning("digest.email_queue_failed", user=user_email)

        await session.commit()
        log.info("digest.sent", period=period, users=sent)
