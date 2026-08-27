"""Email management whitelisted methods."""

from __future__ import annotations

from typing import Any

import aiosmtplib
import structlog

import grunt
from grunt.email.service import SMTP_PASSWORD_MASK, EmailService, smtp_connect_kwargs

logger = structlog.get_logger()


def _mask_password(account: dict[str, Any]) -> dict[str, Any]:
    if account.get("smtp_password"):
        account["smtp_password"] = SMTP_PASSWORD_MASK
    return account


@grunt.whitelist(roles=["superadmin"])
async def test_smtp_connection(
    smtp_server: str,
    smtp_port: int = 587,
    use_tls: bool = True,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Attempt SMTP connect+login without sending a message.

    When ``account_id`` is given and no fresh password was typed, the stored
    password of that account is used (reads mask it, so the form can't send it
    back).
    """
    if account_id and (not smtp_password or smtp_password == SMTP_PASSWORD_MASK):
        smtp_password = await grunt.db.get_value(
            "EmailAccount", account_id, "smtp_password"
        )
    try:
        async with aiosmtplib.SMTP(
            timeout=10,
            **smtp_connect_kwargs(smtp_server, smtp_port, bool(use_tls)),
        ) as smtp:
            if smtp_user and smtp_password:
                await smtp.login(smtp_user, smtp_password)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@grunt.whitelist(roles=["superadmin"])
async def send_test_email(account_id: str, recipient: str) -> dict[str, Any]:
    """Send a short test message through a saved EmailAccount.

    Uses the stored SMTP settings (the caller is a superadmin, so the
    ``after_read`` mask does not apply and the real password is available).
    """
    recipient = (recipient or "").strip()
    if not recipient:
        return {"success": False, "error": "Не вказано адресу отримувача."}

    account = dict(await grunt.get_doc("EmailAccount", account_id))
    if not account.get("enable_outgoing"):
        return {"success": False, "error": "Для цього облікового запису вимкнена вихідна пошта."}

    # Reads mask the password — pull the real one straight from the column.
    account["smtp_password"] = await grunt.db.get_value(
        "EmailAccount", account_id, "smtp_password"
    )
    if not account["smtp_password"]:
        return {"success": False, "error": "Пароль SMTP не збережено. Збережіть обліковий запис із паролем."}

    try:
        await EmailService.send_now(
            account,
            {
                "subject": "Grunt — тестовий лист",
                "recipient": recipient,
                "content": (
                    "Це тестовий лист, надісланий із Grunt.\n\n"
                    "Якщо ви його отримали — надсилання пошти через цей обліковий "
                    "запис працює."
                ),
            },
        )
        return {"success": True}
    except Exception as e:
        logger.warning("email.test_send_failed", account=account_id, error=str(e))
        return {"success": False, "error": str(e)}


@grunt.whitelist(roles=["superadmin"])
async def list_accounts() -> list[dict[str, Any]]:
    result = await grunt.get_list("EmailAccount", limit=1000, order_by="created_at")
    return [_mask_password(dict(acc)) for acc in result]


@grunt.whitelist(roles=["superadmin"])
async def get_account(account_id: str) -> dict[str, Any]:
    data = await grunt.get_doc("EmailAccount", account_id)
    return _mask_password(dict(data))


@grunt.whitelist(roles=["superadmin"])
async def list_queue(
    status: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    page = int(page)
    per_page = int(per_page)
    filters = {"status": status} if status else None
    records = await grunt.get_list(
        "EmailQueue",
        limit=per_page,
        page=page,
        order_by="created_at",
        order="desc",
        filters=filters,
    )
    total = await grunt.count("EmailQueue", filters=filters)
    return {"items": records, "total": total, "page": page, "per_page": per_page}


@grunt.whitelist(roles=["superadmin"])
async def retry_item(queue_id: str) -> bool:
    await grunt.db.set_value("EmailQueue", queue_id, {"status": "Pending", "error_message": None})
    return True
