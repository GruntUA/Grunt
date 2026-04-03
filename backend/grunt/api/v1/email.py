"""Email management API — account config, queue, test connection."""

from __future__ import annotations

from typing import Any

import aiosmtplib
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

logger = structlog.get_logger()
router = APIRouter(prefix="/email", tags=["email"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(user: GruntUser) -> None:
    if not getattr(user, "is_superadmin", False):
        raise HTTPException(403, "Admin only")


async def _get_account_table(session: AsyncSession):  # noqa: ANN201
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    dt = doctype_registry._doctypes.get("EmailAccount")
    if not dt:
        raise HTTPException(503, "EmailAccount DocType not loaded")
    return compile_doctype_to_table(dt)


async def _get_queue_table(session: AsyncSession):  # noqa: ANN201
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    dt = doctype_registry._doctypes.get("EmailQueue")
    if not dt:
        raise HTTPException(503, "EmailQueue DocType not loaded")
    return compile_doctype_to_table(dt)


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
    session: AsyncSession = Depends(get_session),
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
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    _require_admin(user)
    table = await _get_account_table(session)
    result = await session.execute(select(table).order_by(table.c.created_at.desc()))
    rows = [dict(r._mapping) for r in result.fetchall()]
    # Mask password
    for row in rows:
        if row.get("smtp_password"):
            row["smtp_password"] = "••••••••"
    return {"success": True, "data": rows}


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    _require_admin(user)
    table = await _get_account_table(session)
    result = await session.execute(select(table).where(table.c.id == account_id))
    row = result.first()
    if not row:
        raise HTTPException(404, "Account not found")
    data = dict(row._mapping)
    if data.get("smtp_password"):
        data["smtp_password"] = "••••••••"
    return {"success": True, "data": data}


# ── Email Queue ───────────────────────────────────────────────────────────────

@router.get("/queue")
async def list_queue(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    _require_admin(user)
    table = await _get_queue_table(session)
    q = select(table).order_by(table.c.created_at.desc())
    if status:
        q = q.where(table.c.status == status)

    count_q = select(table.c.id)
    if status:
        count_q = count_q.where(table.c.status == status)

    total = len((await session.execute(count_q)).fetchall())
    offset = (page - 1) * per_page
    result = await session.execute(q.offset(offset).limit(per_page))
    rows = [dict(r._mapping) for r in result.fetchall()]

    return {
        "success": True,
        "data": rows,
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.post("/queue/{queue_id}/retry")
async def retry_queue_item(
    queue_id: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    _require_admin(user)
    table = await _get_queue_table(session)
    await session.execute(
        update(table)
        .where(table.c.id == queue_id)
        .values(status="Pending", error_message=None)
    )
    await session.commit()
    return {"success": True}
