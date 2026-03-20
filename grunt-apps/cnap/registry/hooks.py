"""ЦНАП business logic hooks."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update

from grunt.core.hooks import on
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()


@on("before_save")
async def set_deadline_from_service(
    doctype: str, doc: dict[str, Any], user: Any, session: Any, **kwargs: Any
) -> None:
    """Auto-calculate deadline_date from service.deadline_days when creating an Appeal."""
    if doctype != "Appeal":
        return
    if doc.get("deadline_date") or not doc.get("service") or not doc.get("received_date"):
        return

    try:
        svc_dt = await doctype_registry.get("AdminService")
        svc_table = compile_doctype_to_table(svc_dt)
        result = await session.execute(
            select(svc_table.c.deadline_days).where(
                (svc_table.c.id == doc["service"]) | (svc_table.c.name == doc["service"])
            )
        )
        row = result.first()
        if row and row.deadline_days:
            received = doc["received_date"]
            if isinstance(received, str):
                received = date.fromisoformat(received)
            doc["deadline_date"] = (received + timedelta(days=row.deadline_days)).isoformat()
    except Exception:
        logger.exception("cnap.set_deadline_error")


@on("before_save")
async def copy_applicant_fields(
    doctype: str, doc: dict[str, Any], user: Any, session: Any, **kwargs: Any
) -> None:
    """Copy full_name from Applicant and service_name from AdminService into Appeal fields."""
    if doctype != "Appeal":
        return

    # Copy applicant name
    if doc.get("applicant") and not doc.get("applicant_name"):
        try:
            app_dt = await doctype_registry.get("Applicant")
            app_table = compile_doctype_to_table(app_dt)
            result = await session.execute(
                select(app_table.c.full_name, app_table.c.phone, app_table.c.email).where(
                    (app_table.c.id == doc["applicant"]) | (app_table.c.name == doc["applicant"])
                )
            )
            row = result.first()
            if row:
                doc["applicant_name"] = row.full_name
                if not doc.get("applicant_phone") and row.phone:
                    doc["applicant_phone"] = row.phone
                if not doc.get("applicant_email") and row.email:
                    doc["applicant_email"] = row.email
        except Exception:
            logger.exception("cnap.copy_applicant_error")

    # Copy service name
    if doc.get("service") and not doc.get("service_name"):
        try:
            svc_dt = await doctype_registry.get("AdminService")
            svc_table = compile_doctype_to_table(svc_dt)
            result = await session.execute(
                select(svc_table.c.service_name).where(
                    (svc_table.c.id == doc["service"]) | (svc_table.c.name == doc["service"])
                )
            )
            row = result.first()
            if row:
                doc["service_name"] = row.service_name
        except Exception:
            logger.exception("cnap.copy_service_name_error")


@on("on_transition")
async def assign_operator_on_start(
    doctype: str,
    doc: dict[str, Any],
    from_state: str,
    to_state: str,
    user: Any,
    session: Any,
    **kwargs: Any,
) -> None:
    """When Appeal transitions Нове -> В роботі, set operator to current user."""
    if doctype != "Appeal":
        return
    if from_state == "Нове" and to_state == "В роботі":
        if not doc.get("operator"):
            try:
                appeal_dt = await doctype_registry.get("Appeal")
                appeal_table = compile_doctype_to_table(appeal_dt)
                await session.execute(
                    update(appeal_table)
                    .where(appeal_table.c.id == doc["id"])
                    .values(operator=user.email)
                )
                await session.commit()
            except Exception:
                logger.exception("cnap.assign_operator_error")
