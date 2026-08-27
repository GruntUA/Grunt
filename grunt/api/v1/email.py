"""Email management whitelisted methods."""

from __future__ import annotations

from typing import Any

import aiosmtplib
import structlog

import grunt
from grunt.email.service import smtp_connect_kwargs

logger = structlog.get_logger()


def _mask_password(account: dict[str, Any]) -> dict[str, Any]:
    if account.get("smtp_password"):
        account["smtp_password"] = "••••••••"
    return account


@grunt.whitelist(roles=["superadmin"])
async def test_smtp_connection(
    smtp_server: str,
    smtp_port: int = 587,
    use_tls: bool = True,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
) -> dict[str, Any]:
    """Attempt SMTP connect+login without sending a message."""
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
