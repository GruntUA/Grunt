"""Startup — SystemSettings singleton seeding."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()


async def seed_system_settings(session: AsyncSession, engine: AsyncEngine) -> None:
    """Ensure a row exists for the SystemSettings singleton."""
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

    dt = await doctype_registry.get("SystemSettings")
    table = compile_doctype_to_table(dt)

    result = await session.execute(select(table).limit(1))
    if result.first():
        return

    now = datetime.now(timezone.utc)
    row = {
        "id": str(uuid.uuid4()),
        "name": "SystemSettings",
        "owner": "system",
        "created_at": now,
        "modified_at": now,
        "modified_by": "system",
        "docstatus": 0,
        "app_name": "Grunt Framework",
        "language": "uk-UA",
        "timezone": "Europe/Kyiv",
        "date_format": "dd.mm.yyyy",
        "allow_user_registration": False,
    }

    await session.execute(table.insert().values(**row))
    await session.flush()
    logger.info("startup.system_settings_seeded")
