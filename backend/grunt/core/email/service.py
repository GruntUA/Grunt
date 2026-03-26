from __future__ import annotations

import email
from email.message import EmailMessage
from typing import Any

import aioimaplib
import aiosmtplib
import structlog

logger = structlog.get_logger()


class EmailService:
    """Service for asynchronous SMTP and IMAP operations."""

    @staticmethod
    async def send_now(account: dict[str, Any], message: dict[str, Any]) -> None:
        """Send an email immediately using the provided account settings."""
        if not account.get("enable_outgoing"):
            raise ValueError(f"Outgoing email is disabled for account {account.get('email_address')}")

        smtp_server = account.get("smtp_server")
        smtp_port = account.get("smtp_port", 587)
        use_tls = account.get("use_tls", True)
        username = account.get("smtp_user")
        password = account.get("smtp_password")

        # Construct EmailMessage
        msg = EmailMessage()
        msg["Subject"] = message.get("subject", "")
        msg["From"] = account.get("email_address")
        msg["To"] = message.get("recipient")
        msg.set_content(message.get("content", ""))

        try:
            async with aiosmtplib.SMTP(
                hostname=smtp_server,
                port=smtp_port,
                use_tls=use_tls,
            ) as smtp:
                if username and password:
                    await smtp.login(username, password)
                await smtp.send_message(msg)
            
            logger.info(
                "email.sent", 
                recipient=message.get("recipient"), 
                subject=message.get("subject")
            )
        except Exception as e:
            logger.error("email.send_failed", error=str(e), recipient=message.get("recipient"))
            raise

    @staticmethod
    async def pull_emails(account: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch unread emails from the IMAP server."""
        if not account.get("enable_incoming"):
            return []

        imap_server = account.get("imap_server")
        imap_port = account.get("imap_port", 993)
        use_ssl = account.get("use_ssl", True)
        username = account.get("email_address") # Often same as address
        password = account.get("smtp_password") # Use common password for now

        emails: list[dict[str, Any]] = []

        try:
            imap = aioimaplib.IMAP4_SSL(imap_server, imap_port) if use_ssl else aioimaplib.IMAP4(imap_server, imap_port)
            await imap.wait_hello()
            await imap.login(username, password)
            await imap.select("INBOX")

            # Search for unread messages
            status, messages = await imap.search("UNSEEN")
            if status == "OK" and messages[0]:
                for num in messages[0].split():
                    status, data = await imap.fetch(num, "(RFC822)")
                    if status == "OK":
                        raw_email = data[1]
                        msg = email.message_from_bytes(raw_email)
                        
                        # Basic parsing
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode()
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode()

                        emails.append({
                            "sender": msg["From"],
                            "subject": msg["Subject"],
                            "content": body,
                            "date": msg["Date"]
                        })
                        
            await imap.logout()
            logger.info("email.pulled", count=len(emails), account=account.get("email_address"))
            
        except Exception as e:
            logger.error("email.pull_failed", error=str(e), account=account.get("email_address"))
            
        return emails
