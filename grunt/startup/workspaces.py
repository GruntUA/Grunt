"""Startup — workspace (AppMenu + sidebar) seeding.

App-install orchestration (DocTypes, fixtures, print formats) lives in
``grunt.startup.app_install`` — this module only creates/updates the
``AppMenu``/``WorkspaceSidebarItem`` records themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

_FIXTURES_DIR = __import__("pathlib").Path(__file__).parent.parent / "fixtures"


async def seed_grunt_workspace(session: AsyncSession, eng: Any) -> None:
    """Create or update the Grunt system workspace from fixtures/grunt_workspace.json."""
    import json

    from grunt.app import grunt

    fixture_file = _FIXTURES_DIR / "grunt_workspace.json"
    if not fixture_file.exists():
        logger.warning("startup.grunt_workspace_fixture_missing", path=str(fixture_file))
        return

    data: dict[str, Any] = json.loads(fixture_file.read_text(encoding="utf-8"))
    ws_name: str = data["name"]

    async with grunt.system_context(session, eng):
        # Register the grunt framework itself as an installed app (once)
        if await grunt.exists("GruntInstalledApp", {"name": "grunt"}) is None:
            await grunt.new_doc(
                "GruntInstalledApp",
                {
                    "name": "grunt",
                    "title": "Grunt",
                    "version": "0.1.0",
                    "modules": ["core"],
                },
            )
            logger.info("startup.grunt_app_registered")

        existing = await grunt.get_list(
            "AppMenu",
            filters={"name": ws_name},
            fields=["name"],
            limit=1,
        )

        if existing:
            ws_id = existing[0]["name"]
            await grunt.save_doc(
                "AppMenu",
                ws_id,
                {
                    k: v
                    for k, v in {
                        "label": data.get("label"),
                        "icon": data.get("icon"),
                        "color": data.get("color"),
                        "description": data.get("description"),
                        "sequence": data.get("sequence"),
                        "home_page": data.get("home_page"),
                    }.items()
                    if v is not None
                },
            )
            logger.info("startup.grunt_workspace_updating")
        else:
            ws = await grunt.new_doc(
                "AppMenu",
                {
                    "name": ws_name,
                    "label": data["label"],
                    "app": data.get("app", "grunt"),
                    "icon": data.get("icon", ""),
                    "color": data.get("color", ""),
                    "description": data.get("description", ""),
                    "sequence": data.get("sequence", 0),
                    "home_page": data.get("home_page", ""),
                    "is_hidden": data.get("is_hidden", False),
                    "roles": data.get("roles", ""),
                },
            )
            ws_id = ws["name"]

        # Replace sidebar items: bulk-delete old, bulk-insert new
        await grunt.db.delete("WorkspaceSidebarItem", {"parent_name": ws_id})

        items = data.get("sidebar_items", [])
        if items:
            await grunt.bulk_insert(
                "WorkspaceSidebarItem",
                [
                    {
                        "parent_name": ws_id,
                        "parent_doctype": "AppMenu",
                        "parent_field": "sidebar_items",
                        "idx": item_data.get("sequence", i),
                        "section": item_data.get("section", ""),
                        "type": item_data.get("type", "DocType"),
                        "label": item_data.get("label", ""),
                        "icon": item_data.get("icon", ""),
                        "link_to": item_data.get("link_to", ""),
                        "show_count": item_data.get("show_count", False),
                        "count_filters": item_data.get("count_filters", ""),
                        "show_new_btn": item_data.get("show_new_btn", False),
                        "roles": item_data.get("roles", ""),
                    }
                    for i, item_data in enumerate(items)
                ],
            )

    logger.info("startup.grunt_workspace_seeded")


async def _apply_workspace_fixture(
    records: list,
    app_name: str,
    app_meta: dict,
) -> bool:
    """Upsert AppMenu + WorkspaceSidebarItem rows from fixture data."""
    from grunt.app import grunt

    applied = False

    for rec in records:
        ws_name = rec.get("name", app_name)
        existing = await grunt.get_list(
            "AppMenu",
            filters={"name": ws_name},
            fields=["name"],
            limit=1,
        )

        if existing:
            ws_id = existing[0]["name"]
            await grunt.save_doc(
                "AppMenu",
                ws_id,
                {
                    k: v
                    for k, v in {
                        "label": rec.get("label"),
                        "icon": rec.get("icon"),
                        "color": rec.get("color"),
                        "description": rec.get("description"),
                        "sequence": rec.get("sequence"),
                        "roles": rec.get("roles"),
                        "is_hidden": rec.get("is_hidden"),
                        "home_page": rec.get("home_page"),
                    }.items()
                    if v is not None
                },
            )
        else:
            new_ws: dict[str, Any] = {
                "name": ws_name,
                "label": rec.get("label", ws_name),
                "app": rec.get("app", app_name),
                "icon": rec.get("icon", app_meta.get("icon", "📦")),
                "color": rec.get("color", app_meta.get("color", "#2D6A4F")),
                "description": rec.get("description", ""),
                "sequence": rec.get("sequence", 10),
                "is_hidden": rec.get("is_hidden", False),
                "roles": rec.get("roles", ""),
            }
            # home_page is a Link — omit rather than send "" when unset
            if rec.get("home_page"):
                new_ws["home_page"] = rec["home_page"]
            ws = await grunt.new_doc("AppMenu", new_ws)
            ws_id = ws["name"]

        # Replace sidebar items: bulk-delete old, bulk-insert new
        await grunt.db.delete("WorkspaceSidebarItem", {"parent_name": ws_id})

        items = rec.get("sidebar_items", rec.get("items", []))
        if items:
            await grunt.bulk_insert(
                "WorkspaceSidebarItem",
                [
                    {
                        "parent_name": ws_id,
                        "parent_doctype": "AppMenu",
                        "parent_field": "sidebar_items",
                        "idx": item.get("sequence", i),
                        "section": item.get("section", ""),
                        "type": item.get("type", "DocType"),
                        "label": item.get("label", ""),
                        "icon": item.get("icon", ""),
                        "link_to": item.get("link_to", ""),
                        "show_count": item.get("show_count", False),
                        "count_filters": item.get("count_filters", ""),
                        "show_new_btn": item.get("show_new_btn", False),
                        "roles": item.get("roles", ""),
                    }
                    for i, item in enumerate(items)
                ],
            )

        applied = True

    return applied


async def _auto_seed_workspace(
    app_name: str,
    app_meta: dict,
    app_doctypes: list,
) -> None:
    """Create/update workspace from registry DocTypes (fallback when no fixture)."""
    from grunt.app import grunt

    existing = await grunt.get_list(
        "AppMenu",
        filters={"name": app_name},
        fields=["name"],
        limit=1,
    )

    if existing:
        ws_id = existing[0]["name"]
        await grunt.save_doc(
            "AppMenu",
            ws_id,
            {
                "label": app_meta.get("title", app_name),
                "icon": app_meta.get("icon", "📦"),
                "color": app_meta.get("color", "#2D6A4F"),
                "description": app_meta.get("description", ""),
            },
        )
    else:
        ws = await grunt.new_doc(
            "AppMenu",
            {
                "name": app_name,
                "label": app_meta.get("title", app_name),
                "app": app_name,
                "icon": app_meta.get("icon", "📦"),
                "color": app_meta.get("color", "#2D6A4F"),
                "description": app_meta.get("description", ""),
                "sequence": app_meta.get("sequence", 10),
                "is_hidden": False,
                "roles": "",
            },
        )
        ws_id = ws["name"]

    # Replace sidebar items: bulk-delete old, bulk-insert new
    await grunt.db.delete("WorkspaceSidebarItem", {"parent_name": ws_id})

    if app_doctypes:
        await grunt.bulk_insert(
            "WorkspaceSidebarItem",
            [
                {
                    "parent_name": ws_id,
                    "parent_doctype": "AppMenu",
                    "parent_field": "sidebar_items",
                    "idx": seq,
                    "section": app_meta.get("title", app_name),
                    "type": "DocType",
                    "label": dt.label,
                    "icon": "📄",
                    "link_to": dt.name,
                    "show_count": True,
                    "count_filters": "",
                    "show_new_btn": True,
                    "roles": "",
                }
                for seq, dt in enumerate(app_doctypes, start=1)
            ],
        )
