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
        # ── Моніторинг ───────────────────────────────────────────
        {"show_new_btn": False, "sequence": 1},
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
        {
            "section": "Моніторинг",
            "type": "DocType",
            "label": "Лог активності",
            "icon": "📋",
            "link_to": "ActivityLog",
            "show_count": True,
            "show_new_btn": False,
            "sequence": 3,
        },
        # ── Повідомлення ─────────────────────────────────────────
        {
            "section": "Повідомлення",
            "type": "DocType",
            "label": "Правила нотифікацій",
            "icon": "🔔",
            "link_to": "NotificationRule",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 10,
        },
        {
            "section": "Повідомлення",
            "type": "DocType",
            "label": "Нотифікації",
            "icon": "📬",
            "link_to": "Notification",
            "show_count": True,
            "show_new_btn": False,
            "sequence": 11,
        },
        {
            "section": "Повідомлення",
            "type": "DocType",
            "label": "Email акаунти",
            "icon": "📧",
            "link_to": "EmailAccount",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 12,
        },
        {
            "section": "Повідомлення",
            "type": "DocType",
            "label": "Черга листів",
            "icon": "📤",
            "link_to": "EmailQueue",
            "show_count": True,
            "show_new_btn": False,
            "sequence": 13,
        },
        # ── Розробка ─────────────────────────────────────────────
        {
            "section": "Розробка",
            "type": "DocType",
            "label": "Серверні скрипти",
            "icon": "🖥",
            "link_to": "ServerScript",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 20,
        },
        {
            "section": "Розробка",
            "type": "DocType",
            "label": "Клієнтські скрипти",
            "icon": "📜",
            "link_to": "ClientScript",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 21,
        },
        {
            "section": "Розробка",
            "type": "DocType",
            "label": "Веб-форми",
            "icon": "📝",
            "link_to": "WebForm",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 22,
        },
        # ── Дані ─────────────────────────────────────────────────
        {
            "section": "Дані",
            "type": "DocType",
            "label": "Версії документів",
            "icon": "🔄",
            "link_to": "DocVersion",
            "show_count": True,
            "show_new_btn": False,
            "sequence": 30,
        },
        {
            "section": "Дані",
            "type": "DocType",
            "label": "Серії нумерації",
            "icon": "🔢",
            "link_to": "NamingSeries",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 31,
        },
        {
            "section": "Дані",
            "type": "DocType",
            "label": "Зв'язки документів",
            "icon": "🔗",
            "link_to": "DocLink",
            "show_count": True,
            "show_new_btn": False,
            "sequence": 32,
        },
        # ── Друк та шаблони ──────────────────────────────────────
        {
            "section": "Друк та шаблони",
            "type": "DocType",
            "label": "Формати друку",
            "icon": "🖨",
            "link_to": "PrintFormat",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 40,
        },
        # ── Локалізація ──────────────────────────────────────────
        {
            "section": "Локалізація",
            "type": "DocType",
            "label": "Переклади",
            "icon": "🌐",
            "link_to": "Translation",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 50,
        },
        # ── Дашборд ──────────────────────────────────────────────
        {
            "section": "Дашборд",
            "type": "DocType",
            "label": "Графіки",
            "icon": "📊",
            "link_to": "DashboardChart",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 60,
        },
        {
            "section": "Дашборд",
            "type": "DocType",
            "label": "Числові картки",
            "icon": "🔢",
            "link_to": "NumberCard",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 61,
        },
        # ── Система ──────────────────────────────────────────────
        {
            "section": "Система",
            "type": "DocType",
            "label": "Коментарі",
            "icon": "💬",
            "link_to": "Comment",
            "show_count": True,
            "show_new_btn": False,
            "sequence": 70,
        },
    ],
}


async def seed_grunt_workspace(session: AsyncSession) -> None:
    """Create or update the Grunt system workspace and its sidebar items."""
    result = await session.execute(
        select(GruntWorkspace).where(GruntWorkspace.name == "grunt")
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        ws_id = existing.id
        # Update workspace metadata
        existing.label = GRUNT_WORKSPACE["label"]
        existing.icon = GRUNT_WORKSPACE["icon"]
        existing.color = GRUNT_WORKSPACE["color"]
        existing.description = GRUNT_WORKSPACE["description"]
        existing.sequence = GRUNT_WORKSPACE["sequence"]
        # Delete old links and re-seed
        from sqlalchemy import delete  # noqa: PLC0415

        await session.execute(
            delete(GruntWorkspaceLink).where(
                GruntWorkspaceLink.workspace_id == ws_id
            )
        )
        await session.flush()
        logger.info("startup.grunt_workspace_updating")
    else:
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


# ── Auto-seed workspaces for installed apps ──────────────────────────────


async def seed_app_workspaces(session: AsyncSession, site_name: str) -> None:
    """Auto-create workspaces for installed apps that don't have one yet.

    Reads ``grunt.site`` → ``installed_apps``, loads each app's metadata
    (``grunt_app.py`` or ``app.json``), and creates a workspace with the
    app's DocTypes as sidebar items.
    """
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from grunt.core.site.manager import site_manager  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    site_file = site_manager.sites_dir / site_name / "grunt.site"
    if not site_file.exists():
        return

    site_config = json.loads(site_file.read_text())
    installed_apps = site_config.get("installed_apps", [])

    from sqlalchemy import delete as sa_delete  # noqa: PLC0415

    for app_name in installed_apps:
        if app_name == "grunt":
            continue  # already handled by seed_grunt_workspace

        # Load app metadata
        app_dir = site_manager.bench_dir / "apps" / app_name
        app_meta = _load_app_meta(app_dir)
        if app_meta is None:
            logger.warning("startup.app_meta_not_found", app=app_name)
            continue

        # Gather the app's DocTypes from registry (matching module)
        all_doctypes = await doctype_registry.list_all()
        app_modules = set(app_meta.get("modules", []))
        app_doctypes = [
            dt for dt in all_doctypes
            if dt.module in app_modules and not dt.is_child
        ]

        # Check if workspace already exists
        result = await session.execute(
            select(GruntWorkspace).where(GruntWorkspace.name == app_name)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            ws_id = existing.id
            # Update metadata
            existing.label = app_meta.get("title", app_name)
            existing.icon = app_meta.get("icon", "📦")
            existing.color = app_meta.get("color", "#2D6A4F")
            existing.description = app_meta.get("description", "")
            # Delete old links and re-seed
            await session.execute(
                sa_delete(GruntWorkspaceLink).where(
                    GruntWorkspaceLink.workspace_id == ws_id
                )
            )
            await session.flush()
        else:
            ws_id = str(uuid.uuid4())
            ws = GruntWorkspace(
                id=ws_id,
                name=app_name,
                label=app_meta.get("title", app_name),
                app=app_name,
                icon=app_meta.get("icon", "📦"),
                color=app_meta.get("color", "#2D6A4F"),
                description=app_meta.get("description", ""),
                sequence=app_meta.get("sequence", 10),
                is_hidden=False,
                roles="",
            )
            session.add(ws)
            await session.flush()

        # Add header separator
        session.add(GruntWorkspaceLink(
            id=str(uuid.uuid4()),
            workspace_id=ws_id,
            section="",
            type="DocType",
            label="",
            icon="",
            link_to="",
            show_count=False,
            count_filters="",
            show_new_btn=False,
            roles="",
            sequence=0,
        ))

        # Add DocType items
        for seq, dt in enumerate(app_doctypes, start=1):
            session.add(GruntWorkspaceLink(
                id=str(uuid.uuid4()),
                workspace_id=ws_id,
                section=app_meta.get("title", app_name),
                type="DocType",
                label=dt.label,
                icon="📄",
                link_to=dt.name,
                show_count=True,
                count_filters="",
                show_new_btn=True,
                roles="",
                sequence=seq,
            ))

        logger.info(
            "startup.app_workspace_seeded",
            app=app_name,
            items=len(app_doctypes),
        )


def _load_app_meta(app_dir: "Path") -> dict | None:
    """Load app metadata from grunt_app.py or app.json."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    app_json = app_dir / "app.json"
    if app_json.exists():
        return json.loads(app_json.read_text())

    grunt_app = app_dir / "grunt_app.py"
    if grunt_app.exists():
        ns: dict = {}
        exec(grunt_app.read_text(), ns)  # noqa: S102
        return {
            "name": ns.get("APP_NAME", app_dir.name),
            "title": ns.get("APP_TITLE", app_dir.name),
            "version": ns.get("APP_VERSION", "0.1.0"),
            "modules": ns.get("MODULES", []),
            "icon": ns.get("APP_ICON", "📦"),
            "color": ns.get("APP_COLOR", "#2D6A4F"),
            "description": ns.get("APP_DESCRIPTION", ""),
        }

    return None
