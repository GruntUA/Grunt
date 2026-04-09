"""Email management API — account config, queue, test connection."""

from __future__ import annotations

from typing import Any

import aiosmtplib
import structlog
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel

from grunt.api.router import GruntRouter
from grunt.app import grunt

logger = structlog.get_logger()
router = GruntRouter(prefix="", tags=["email"])


# ── Dependencies ──────────────────────────────────────────────────────────────


def _require_admin(user: Any) -> None:
    if not getattr(user, "is_superadmin", False):
        raise HTTPException(403, "Admin only")


def _mask_password(account: dict[str, Any]) -> dict[str, Any]:
    if account.get("smtp_password"):
        account["smtp_password"] = "••••••••"
    return account


# ── Test connection ───────────────────────────────────────────────────────────


class TestConnectionRequest(BaseModel):
    smtp_server: str
    smtp_port: int = 587
    use_tls: bool = True
    smtp_user: str | None = None
    smtp_password: str | None = None


@router.post("/test-connection")
async def test_smtp_connection(
    body: TestConnectionRequest,
) -> dict[str, Any]:
    """Attempt SMTP connect+login without sending a message."""
    _require_admin(grunt.session)
    try:
        async with aiosmtplib.SMTP(
            hostname=body.smtp_server,
            port=body.smtp_port,
            use_tls=body.use_tls,
            timeout=10,
        ) as smtp:
            if body.smtp_user and body.smtp_password:
                await smtp.login(body.smtp_user, body.smtp_password)
        return {"success": True}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e)}


# ── Email Accounts ────────────────────────────────────────────────────────────


@router.get("/accounts")
async def list_email_accounts() -> dict[str, Any]:
    _require_admin(grunt.session)
    result = await grunt.get_list("EmailAccount", limit=10000, order_by="created_at")
    return {
        "success": True,
        "data": [_mask_password(dict(acc)) for acc in result],
    }


@router.get("/accounts/{account_id}")
async def get_email_account(
    account_id: str,
) -> dict[str, Any]:
    _require_admin(grunt.session)
    data = await grunt.get_doc("EmailAccount", account_id)
    return {"success": True, "data": _mask_password(dict(data))}


# ── Email Queue ───────────────────────────────────────────────────────────────


@router.get("/queue")
async def list_queue(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    _require_admin(grunt.session)
    
    offset = (page - 1) * per_page
    
    records = await grunt.get_list(
        "EmailQueue",
        limit=per_page,
        offset=offset,
        order_by="created_at desc",
        filters={"status": status} if status else None,
    )
    
    total = await grunt.count("EmailQueue", filters={"status": status} if status else None)
    
    return {
        "success": True,
        "data": records,
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.post("/communications")
async def create_communication(
    body: dict[str, Any],
) -> dict[str, Any]:
    _require_admin(grunt.session)
    await grunt.db.set_value(
        "EmailQueue", queue_id, {"status": "Pending", "error_message": None}
    )


@router.post("/queue/{queue_id}/retry")
async def retry_queue_item(
    queue_id: str,
) -> dict[str, Any]:
    _require_admin(grunt.session)
    await grunt.db.set_value(
        "EmailQueue", queue_id, {"status": "Pending", "error_message": None}
    )
    return {"success": True}
