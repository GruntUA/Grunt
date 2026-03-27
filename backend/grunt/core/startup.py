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

_CORE_DOCTYPES_DIR = __import__("pathlib").Path(__file__).parent / "doctypes"


# ── Load built-in core DocTypes ───────────────────────────────────────────


async def load_core_doctypes(session: AsyncSession, engine: AsyncEngine) -> None:
    """Register DocTypes defined as JSON files in grunt/core/doctypes/.

    These are first-class framework DocTypes (Dashboard, Report, etc.)
    that live in the grunt package itself rather than in external apps.
    """
    import json  # noqa: PLC0415

    from grunt.core.metadata.doctype import DocType  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    if not _CORE_DOCTYPES_DIR.exists():
        return

    for dt_file in sorted(_CORE_DOCTYPES_DIR.glob("*.json")):
        try:
            dt_data = json.loads(dt_file.read_text(encoding="utf-8"))
            dt_name = dt_data.get("name", "")
            if not dt_name:
                continue
            if dt_name in doctype_registry._doctypes:
                continue  # already registered (hot-reload)
            dt_obj = DocType.model_validate(dt_data)
            await doctype_registry.register(dt_obj, session, engine)
            await session.flush()
            logger.info("startup.core_doctype_registered", doctype=dt_name)
        except Exception as e:  # noqa: BLE001
            logger.warning("startup.core_doctype_failed", file=dt_file.name, error=str(e))


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
        # ── Дашборди ─────────────────────────────────────────────
        {
            "section": "Дашборди",
            "type": "DocType",
            "label": "Дашборди",
            "icon": "📊",
            "link_to": "Dashboard",
            "show_count": True,
            "show_new_btn": True,
            "sequence": 60,
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
    (``grunt_app.py`` or ``app.json``), auto-registers DocTypes from the app's
    ``doctypes/`` directories if not yet in the registry, and creates a workspace
    with the app's DocTypes as sidebar items.
    """
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from grunt.core.site.manager import site_manager  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.doctype import DocType  # noqa: PLC0415

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

        # Auto-register DocTypes from app's module doctypes directories
        app_modules = set(app_meta.get("modules", []))
        eng = site_manager.get_engine(site_name)
        for module in app_modules:
            doctypes_dir = app_dir / module / "doctypes"
            if not doctypes_dir.exists():
                continue
            for dt_file in sorted(doctypes_dir.glob("*.json")):
                try:
                    dt_data = json.loads(dt_file.read_text(encoding="utf-8"))
                    dt_name = dt_data.get("name", "")
                    if dt_name and dt_name not in doctype_registry._doctypes:
                        dt_obj = DocType.model_validate(dt_data)
                        await doctype_registry.register(dt_obj, session, eng)
                        await session.flush()
                        logger.info("startup.app_doctype_registered", app=app_name, doctype=dt_name)
                except Exception as e:  # noqa: BLE001
                    logger.warning("startup.app_doctype_register_failed", app=app_name, file=dt_file.name, error=str(e))

        # Apply fixtures from all module fixture directories
        workspace_from_fixture = False
        for module in app_modules:
            fixtures_dir = app_dir / module / "fixtures"
            if not fixtures_dir.exists():
                continue
            for fx_file in sorted(fixtures_dir.glob("*.json")):
                try:
                    fx = json.loads(fx_file.read_text(encoding="utf-8"))
                    fx_doctype = fx.get("doctype", "")
                    records = fx.get("records", [])

                    if fx_doctype == "GruntWorkspace":
                        workspace_from_fixture = await _apply_workspace_fixture(
                            records, app_name, app_meta, session
                        )
                    else:
                        await _apply_doctype_fixture(fx_doctype, records, session, eng)

                    logger.info("startup.fixture_applied", app=app_name, file=fx_file.name)
                except Exception as e:  # noqa: BLE001
                    logger.warning("startup.fixture_failed", app=app_name, file=fx_file.name, error=str(e))

        # Auto-seed workspace from registry if no fixture provided one
        if not workspace_from_fixture:
            all_doctypes = await doctype_registry.list_all()
            app_doctypes = [
                dt for dt in all_doctypes
                if dt.module in app_modules and not dt.is_child
            ]
            await _auto_seed_workspace(app_name, app_meta, app_doctypes, session)

        logger.info("startup.app_workspace_seeded", app=app_name)


async def _apply_workspace_fixture(
    records: list,
    app_name: str,
    app_meta: dict,
    session: AsyncSession,
) -> bool:
    """Upsert GruntWorkspace + GruntWorkspaceLink rows from fixture data.

    Returns True if at least one workspace record was processed.
    """
    from sqlalchemy import delete as sa_delete  # noqa: PLC0415

    applied = False
    for rec in records:
        ws_name = rec.get("name", app_name)
        result = await session.execute(
            select(GruntWorkspace).where(GruntWorkspace.name == ws_name)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            ws_id = existing.id
            existing.label = rec.get("label", existing.label)
            existing.icon = rec.get("icon", existing.icon)
            existing.color = rec.get("color", existing.color)
            existing.description = rec.get("description", existing.description)
            existing.sequence = rec.get("sequence", existing.sequence)
            existing.roles = rec.get("roles", existing.roles)
            existing.is_hidden = rec.get("is_hidden", existing.is_hidden)
            await session.execute(
                sa_delete(GruntWorkspaceLink).where(
                    GruntWorkspaceLink.workspace_id == ws_id
                )
            )
        else:
            ws_id = str(uuid.uuid4())
            session.add(GruntWorkspace(
                id=ws_id,
                name=ws_name,
                label=rec.get("label", ws_name),
                app=rec.get("app", app_name),
                icon=rec.get("icon", app_meta.get("icon", "📦")),
                color=rec.get("color", app_meta.get("color", "#2D6A4F")),
                description=rec.get("description", ""),
                sequence=rec.get("sequence", 10),
                is_hidden=rec.get("is_hidden", False),
                roles=rec.get("roles", ""),
            ))

        await session.flush()

        for item in rec.get("items", []):
            session.add(GruntWorkspaceLink(
                id=str(uuid.uuid4()),
                workspace_id=ws_id,
                section=item.get("section", ""),
                type=item.get("type", "DocType"),
                label=item.get("label", ""),
                icon=item.get("icon", ""),
                link_to=item.get("link_to", ""),
                show_count=item.get("show_count", False),
                count_filters=item.get("count_filters", ""),
                show_new_btn=item.get("show_new_btn", False),
                roles=item.get("roles", ""),
                sequence=item.get("sequence", 0),
            ))

        await session.flush()
        applied = True

    return applied


async def _apply_doctype_fixture(
    doctype_name: str,
    records: list,
    session: AsyncSession,
    eng: AsyncEngine,
) -> None:
    """Insert fixture records for a regular DocType, skipping duplicates."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.compiler import compile_doctype_to_table, get_table_name  # noqa: PLC0415

    try:
        dt = await doctype_registry.get(doctype_name)
    except Exception:  # noqa: BLE001
        logger.warning("startup.fixture_doctype_not_found", doctype=doctype_name)
        return

    table = compile_doctype_to_table(dt)
    now = datetime.now(timezone.utc)

    for rec in records:
        # Determine the name key for duplicate check
        name_val = rec.get("name") or rec.get(dt.title_field or "") or str(_uuid.uuid4())[:8]

        # Skip if a record with this name already exists
        exists = await session.execute(
            table.select().where(table.c.name == name_val).limit(1)
        )
        if exists.first():
            continue

        row: dict = {
            "id": str(_uuid.uuid4()),
            "name": name_val,
            "owner": "system",
            "created_at": now,
            "modified_at": now,
            "modified_by": "system",
            "docstatus": 0,
        }
        for field in dt.fields:
            from grunt.core.metadata.field import NON_PHYSICAL_FIELDS  # noqa: PLC0415
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
            if field.fieldname in rec:
                row[field.fieldname] = rec[field.fieldname]
            elif field.default is not None:
                row[field.fieldname] = field.default

        await session.execute(table.insert().values(**row))

    await session.flush()


async def _auto_seed_workspace(
    app_name: str,
    app_meta: dict,
    app_doctypes: list,
    session: AsyncSession,
) -> None:
    """Create/update workspace from registry DocTypes (fallback when no fixture)."""
    from sqlalchemy import delete as sa_delete  # noqa: PLC0415

    result = await session.execute(
        select(GruntWorkspace).where(GruntWorkspace.name == app_name)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        ws_id = existing.id
        existing.label = app_meta.get("title", app_name)
        existing.icon = app_meta.get("icon", "📦")
        existing.color = app_meta.get("color", "#2D6A4F")
        existing.description = app_meta.get("description", "")
        await session.execute(
            sa_delete(GruntWorkspaceLink).where(GruntWorkspaceLink.workspace_id == ws_id)
        )
        await session.flush()
    else:
        ws_id = str(uuid.uuid4())
        session.add(GruntWorkspace(
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
        ))
        await session.flush()

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

    await session.flush()


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
