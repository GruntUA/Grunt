"""Startup routines — populate system DocType tables and seed core data.

Called once during application lifespan startup.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.db.system_tables import (
    GruntMetaDoctype,
    GruntWorkspace,
    GruntWorkspaceLink,
)
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.system_doctypes import SYSTEM_DOCTYPES

logger = structlog.get_logger()


# ── Populate system DocType document tables ──────────────────────────────


async def populate_system_doctypes(
    session: AsyncSession,
    engine: AsyncEngine,
) -> None:
    """Ensure every registered DocType has a row in the ``DocType`` document table.

    This keeps the DocType list view in sync with the registry.
    """
    dt_def = SYSTEM_DOCTYPES["DocType"]
    table = compile_doctype_to_table(dt_def)

    # Get all registered DocTypes from the registry
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    all_doctypes = await doctype_registry.list_all()

    # Get existing rows in the DocType document table
    conn = await session.connection()
    try:
        result = await conn.execute(select(table.c.name))
        existing_names = {row[0] for row in result}
    except Exception:
        # Table might not exist yet on first run
        existing_names = set()

    now = datetime.now(timezone.utc)

    for dt in all_doctypes:
        if dt.name in existing_names:
            # Update existing row
            await conn.execute(
                table.update()
                .where(table.c.name == dt.name)
                .values(
                    label=dt.label,
                    module=dt.module,
                    is_child=dt.is_child,
                    modified_at=now,
                )
            )
        else:
            # Insert new row
            await conn.execute(
                table.insert().values(
                    id=str(uuid.uuid4()),
                    name=dt.name,
                    label=dt.label,
                    module=dt.module,
                    is_child=dt.is_child,
                    owner="system",
                    created_at=now,
                    modified_at=now,
                    modified_by="system",
                    docstatus=0,
                )
            )

    # Remove rows for DocTypes that no longer exist in the registry
    registered_names = {dt.name for dt in all_doctypes}
    stale = existing_names - registered_names
    for name in stale:
        await conn.execute(table.delete().where(table.c.name == name))

    if stale:
        logger.info("startup.doctype_table_cleaned", removed=sorted(stale))
    logger.info("startup.doctype_table_synced", count=len(all_doctypes))


# ── Seed Grunt workspace ─────────────────────────────────────────────────


GRUNT_WORKSPACE: dict[str, Any] = {
    "name": "grunt",
    "label": "Ґрунт",
    "app": "grunt",
    "icon": "⚙",
    "color": "#374151",
    "description": "Налаштування системи",
    "sequence": 999,
    "is_hidden": False,
    "roles": "",  # superadmin only enforced by workspace access logic
    "items": [
        {
            "show_new_btn": False,
            "sequence": 1,
        },
        {
            "section": "Моніторинг",
            "type": "DocType",
            "label": "Фонові завдання",
            "icon": "⏳",
            "link_to": "BackgroundTaskLog",
            "show_count": True,
            "show_new_btn": False,
            "sequence": 2,
        },
    ],
}


async def seed_grunt_workspace(session: AsyncSession) -> None:
    """Create the Grunt system workspace if it doesn't exist."""
    result = await session.execute(
        select(GruntWorkspace).where(GruntWorkspace.name == "grunt")
    )
    if result.scalar_one_or_none() is not None:
        return  # already exists

    ws_id = str(uuid.uuid4())
    ws = GruntWorkspace(
        id=ws_id,
        name=GRUNT_WORKSPACE["name"],
        label=GRUNT_WORKSPACE["label"],
        app=GRUNT_WORKSPACE["app"],
        icon=GRUNT_WORKSPACE["icon"],
        color=GRUNT_WORKSPACE["color"],
        description=GRUNT_WORKSPACE["description"],
        sequence=GRUNT_WORKSPACE["sequence"],
        is_hidden=GRUNT_WORKSPACE["is_hidden"],
        roles=GRUNT_WORKSPACE["roles"],
    )
    session.add(ws)
    await session.flush()

    for item_data in GRUNT_WORKSPACE["items"]:
        link = GruntWorkspaceLink(
            id=str(uuid.uuid4()),
            workspace_id=ws_id,
            section=item_data.get("section", ""),
            type=item_data.get("type", "DocType"),
            label=item_data.get("label", ""),
            icon=item_data.get("icon", ""),
            link_to=item_data.get("link_to", ""),
            show_count=item_data.get("show_count", False),
            count_filters=item_data.get("count_filters", ""),
            show_new_btn=item_data.get("show_new_btn", False),
            roles=item_data.get("roles", ""),
            sequence=item_data.get("sequence", 0),
        )
        session.add(link)

    logger.info("startup.grunt_workspace_seeded")
