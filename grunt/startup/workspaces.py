"""Startup — workspace seeding for Grunt core and installed apps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

_FIXTURES_DIR = __import__("pathlib").Path(__file__).parent.parent / "fixtures"


async def seed_grunt_workspace(session: AsyncSession, eng: Any) -> None:
    """Create or update the Grunt system workspace from fixtures/grunt_workspace.json."""
    import json  # noqa: PLC0415

    from grunt.app import grunt  # noqa: PLC0415

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
            fields=["id"],
            limit=1,
        )

        if existing:
            ws_id = existing[0]["id"]
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
                    "is_hidden": data.get("is_hidden", False),
                    "roles": data.get("roles", ""),
                },
            )
            ws_id = ws["id"]

        # Replace sidebar items: bulk-delete old, bulk-insert new
        await grunt.db.delete("WorkspaceSidebarItem", {"parent_id": ws_id})

        items = data.get("sidebar_items", [])
        if items:
            await grunt.bulk_insert(
                "WorkspaceSidebarItem",
                [
                    {
                        "parent_id": ws_id,
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


async def seed_app_workspaces(session: AsyncSession, site_name: str) -> None:
    """Auto-create workspaces for installed apps that don't have one yet.

    Reads ``grunt.site`` → ``installed_apps``, loads each app's metadata
    (``grunt_app.py`` or ``app.json``), auto-registers DocTypes from the app's
    ``doctypes/`` directories if not yet in the registry, and creates a workspace
    with the app's DocTypes as sidebar items.
    """
    import json  # noqa: PLC0415

    from grunt.app import grunt  # noqa: PLC0415
    from grunt.metadata.doctype import DocType  # noqa: PLC0415
    from grunt.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.site.manager import site_manager  # noqa: PLC0415
    from grunt.startup.fixtures import _apply_doctype_fixture, _load_app_meta  # noqa: PLC0415

    site_file = site_manager.sites_dir / site_name / "grunt.site"
    if not site_file.exists():
        return

    site_config = json.loads(site_file.read_text())
    installed_apps = site_config.get("installed_apps", [])
    eng = site_manager.get_engine(site_name)

    async with grunt.system_context(session, eng):
        await doctype_registry.load_all(session)

        for app_name in installed_apps:
            if app_name == "grunt":
                continue  # already handled by seed_grunt_workspace

            app_dir = site_manager.bench_dir / "apps" / app_name
            app_meta = _load_app_meta(app_dir)
            if app_meta is None:
                logger.warning("startup.app_meta_not_found", app=app_name)
                continue

            # Ensure app is registered in GruntInstalledApp table
            is_first_install = await grunt.exists("GruntInstalledApp", {"name": app_name}) is None
            if is_first_install:
                await grunt.new_doc(
                    "GruntInstalledApp",
                    {
                        "name": app_name,
                        "title": app_meta.get("title", app_name),
                        "version": app_meta.get("version", "0.1.0"),
                        "modules": app_meta.get("modules", []),
                    },
                )
                logger.info("startup.app_registered", app=app_name)

            app_modules = set(app_meta.get("modules", []))

            # Auto-register DocTypes — meta-level operation, stays on registry/SA
            for module in app_modules:
                doctypes_dir = app_dir / module / "doctypes"
                if not doctypes_dir.exists():
                    continue
                for dt_dir in sorted(doctypes_dir.iterdir()):
                    if not dt_dir.is_dir() or dt_dir.name.startswith((".", "_")):
                        continue
                    dt_file = dt_dir / f"{dt_dir.name}.json"
                    if not dt_file.exists():
                        continue
                    try:
                        dt_data = json.loads(dt_file.read_text(encoding="utf-8"))
                        dt_name = dt_data.get("name", "")
                        if not dt_name:
                            continue
                        dt_obj = DocType.model_validate(dt_data)
                        if not dt_obj.app:
                            dt_obj.app = app_name
                        if dt_name not in doctype_registry._doctypes:
                            async with session.begin_nested():
                                await doctype_registry.register(dt_obj, session, eng)
                            logger.info(
                                "startup.app_doctype_registered", app=app_name, doctype=dt_name
                            )
                        else:
                            existing_dt = doctype_registry._doctypes[dt_name]
                            if existing_dt.model_dump(mode="json") != dt_obj.model_dump(
                                mode="json"
                            ):
                                async with session.begin_nested():
                                    await doctype_registry.update(dt_obj, session, eng)
                                logger.info(
                                    "startup.app_doctype_updated", app=app_name, doctype=dt_name
                                )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "startup.app_doctype_register_failed",
                            app=app_name,
                            file=dt_file.name,
                            error=str(e),
                        )

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

                        if fx_doctype == "AppMenu":
                            workspace_from_fixture = await _apply_workspace_fixture(
                                records, app_name, app_meta
                            )
                        else:
                            await _apply_doctype_fixture(fx_doctype, records, session, eng)

                        logger.info("startup.fixture_applied", app=app_name, file=fx_file.name)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "startup.fixture_failed", app=app_name, file=fx_file.name, error=str(e)
                        )

            # Auto-register PrintFormats from app's module print_formats directories
            for module in app_modules:
                pf_dir = app_dir / module / "print_formats"
                if not pf_dir.exists():
                    continue
                for pf_meta in sorted(pf_dir.glob("*.json")):
                    try:
                        data = json.loads(pf_meta.read_text(encoding="utf-8"))
                        base_name = pf_meta.stem
                        html_file = pf_dir / f"{base_name}.html"
                        if html_file.exists():
                            data["template"] = html_file.read_text(encoding="utf-8")
                        await _apply_doctype_fixture("PrintFormat", [data], session, eng)
                        logger.info(
                            "startup.print_format_registered", app=app_name, name=data.get("name")
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "startup.print_format_failed",
                            app=app_name,
                            file=pf_meta.name,
                            error=str(e),
                        )

            # Auto-seed workspace from registry if no fixture provided one
            if not workspace_from_fixture:
                all_doctypes = await doctype_registry.list_all()
                app_doctypes = [
                    dt for dt in all_doctypes if dt.module in app_modules and not dt.is_child
                ]
                await _auto_seed_workspace(app_name, app_meta, app_doctypes)

            # Run after_install hook on first installation
            if is_first_install:
                install_module_path = app_dir / "install.py"
                if install_module_path.exists():
                    try:
                        import importlib.util  # noqa: PLC0415

                        spec = importlib.util.spec_from_file_location(
                            f"{app_name}.install", install_module_path
                        )
                        if spec and spec.loader:
                            install_mod = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(install_mod)
                            if hasattr(install_mod, "after_install"):
                                await install_mod.after_install(session, site_name)
                                logger.info("startup.after_install_ok", app=app_name)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("startup.after_install_failed", app=app_name, error=str(e))

            logger.info("startup.app_workspace_seeded", app=app_name)


async def _apply_workspace_fixture(
    records: list,
    app_name: str,
    app_meta: dict,
) -> bool:
    """Upsert AppMenu + WorkspaceSidebarItem rows from fixture data."""
    from grunt.app import grunt  # noqa: PLC0415

    applied = False

    for rec in records:
        ws_name = rec.get("name", app_name)
        existing = await grunt.get_list(
            "AppMenu",
            filters={"name": ws_name},
            fields=["id"],
            limit=1,
        )

        if existing:
            ws_id = existing[0]["id"]
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
                    }.items()
                    if v is not None
                },
            )
        else:
            ws = await grunt.new_doc(
                "AppMenu",
                {
                    "name": ws_name,
                    "label": rec.get("label", ws_name),
                    "app": rec.get("app", app_name),
                    "icon": rec.get("icon", app_meta.get("icon", "📦")),
                    "color": rec.get("color", app_meta.get("color", "#2D6A4F")),
                    "description": rec.get("description", ""),
                    "sequence": rec.get("sequence", 10),
                    "is_hidden": rec.get("is_hidden", False),
                    "roles": rec.get("roles", ""),
                },
            )
            ws_id = ws["id"]

        # Replace sidebar items: bulk-delete old, bulk-insert new
        await grunt.db.delete("WorkspaceSidebarItem", {"parent_id": ws_id})

        items = rec.get("sidebar_items", rec.get("items", []))
        if items:
            await grunt.bulk_insert(
                "WorkspaceSidebarItem",
                [
                    {
                        "parent_id": ws_id,
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
    from grunt.app import grunt  # noqa: PLC0415

    existing = await grunt.get_list(
        "AppMenu",
        filters={"name": app_name},
        fields=["id"],
        limit=1,
    )

    if existing:
        ws_id = existing[0]["id"]
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
        ws_id = ws["id"]

    # Replace sidebar items: bulk-delete old, bulk-insert new
    await grunt.db.delete("WorkspaceSidebarItem", {"parent_id": ws_id})

    if app_doctypes:
        await grunt.bulk_insert(
            "WorkspaceSidebarItem",
            [
                {
                    "parent_id": ws_id,
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
