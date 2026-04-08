"""Email management API — account config, queue, test connection."""

from __future__ import annotations

from typing import Any

import aiosmtplib
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_engine, get_session
from grunt.core.document.service import DocumentService

logger = structlog.get_logger()
router = APIRouter(prefix="/email", tags=["email"])


# ── Dependencies ──────────────────────────────────────────────────────────────


def _require_admin(user: GruntUser) -> None:
    if not getattr(user, "is_superadmin", False):
        raise HTTPException(403, "Admin only")


def _mask_password(account: dict[str, Any]) -> dict[str, Any]:
    if account.get("smtp_password"):
        account["smtp_password"] = "••••••••"
    return account


def get_doc_service(
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
) -> DocumentService:
    return DocumentService(session, engine)


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
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Attempt SMTP connect+login without sending a message."""
    _require_admin(user)
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
async def list_accounts(
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    _require_admin(user)
    result = await svc.list_documents("EmailAccount", user, per_page=10000, sort_by="created_at")
    return {
        "success": True,
        "data": [_mask_password(acc) for acc in result["data"]],
    }


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    _require_admin(user)
    data = await svc.get_document("EmailAccount", account_id, user)
    return {"success": True, "data": _mask_password(data)}


# ── Email Queue ───────────────────────────────────────────────────────────────


@router.get("/queue")
async def list_queue(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    _require_admin(user)
    return await svc.list_documents(
        "EmailQueue",
        user,
        page=page,
        per_page=per_page,
        sort_by="created_at",
        filters={"status": status} if status else None,
    )


@router.post("/queue/{queue_id}/retry")
async def retry_queue_item(
    queue_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    _require_admin(user)
    from grunt.app import grunt  # noqa: PLC0415

    tokens = grunt.set_context(session=svc.session, engine=svc.engine, user=user)
    try:
        await grunt.db.set_value(
            "EmailQueue", queue_id, {"status": "Pending", "error_message": None}
        )
    finally:
        grunt.reset_context(tokens)
    return {"success": True}
