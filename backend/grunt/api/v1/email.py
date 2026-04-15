"""Email management whitelisted methods."""

from __future__ import annotations

from typing import Any

import aiosmtplib
import structlog

import grunt

logger = structlog.get_logger()


def _require_admin() -> None:
    from grunt.app import grunt as grunt_app
    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt.throw("Admin only", "PERMISSION_DENIED")


def _mask_password(account: dict[str, Any]) -> dict[str, Any]:
    if account.get("smtp_password"):
        account["smtp_password"] = "••••••••"
    return account


@grunt.whitelist()
async def test_smtp_connection(
    smtp_server: str,
    smtp_port: int = 587,
    use_tls: bool = True,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
) -> dict[str, Any]:
    """Attempt SMTP connect+login without sending a message."""
    _require_admin()
    try:
        async with aiosmtplib.SMTP(
            hostname=smtp_server,
            port=int(smtp_port),
            use_tls=bool(use_tls),
            timeout=10,
        ) as smtp:
            if smtp_user and smtp_password:
                await smtp.login(smtp_user, smtp_password)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@grunt.whitelist()
async def list_accounts() -> list[dict[str, Any]]:
    _require_admin()
    result = await grunt.get_list("EmailAccount", limit=1000, order_by="created_at")
    return [_mask_password(dict(acc)) for acc in result]


@grunt.whitelist()
async def get_account(account_id: str) -> dict[str, Any]:
    _require_admin()
    data = await grunt.get_doc("EmailAccount", account_id)
    return _mask_password(dict(data))


@grunt.whitelist()
async def list_queue(
    status: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    _require_admin()
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


@grunt.whitelist()
async def retry_item(queue_id: str) -> bool:
    _require_admin()
    await grunt.db.set_value(
        "EmailQueue", queue_id, {"status": "Pending", "error_message": None}
    )
    return True
