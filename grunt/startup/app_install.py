"""Startup — sync installed apps: DocTypes, fixtures, print formats, workspace.

Runs on every ``grunt migrate`` / ``grunt app install`` / ``grunt site create``:
re-reads each installed app's metadata from disk and applies it to the DB.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def sync_installed_apps(session: AsyncSession, site_name: str) -> None:
    """Sync DocTypes, fixtures, print formats and the workspace for every installed app.

    Reads ``grunt.site`` → ``installed_apps``, loads each app's metadata
    (``grunt_app.py`` or ``app.json``), auto-registers DocTypes from the app's
    ``doctypes/`` directories if not yet in the registry, applies fixtures and
    print formats, then creates/updates a workspace with the app's DocTypes as
    sidebar items.
    """
    import json

    from grunt.app import grunt
    from grunt.metadata.doctype import DocType
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import site_manager
    from grunt.startup.fixtures import _apply_doctype_fixture, _load_app_meta
    from grunt.startup.workspaces import _apply_workspace_fixture, _auto_seed_workspace

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
                    except Exception as e:
                        logger.warning(
                            "startup.app_doctype_register_failed",
                            app=app_name,
                            file=dt_file.name,
                            error=str(e),
                        )

            # Apply fixtures from all module fixture directories.
            # AppMenu fixtures are deferred to the end: they may reference records
            # created by other fixtures (e.g. home_page -> Page).
            workspace_from_fixture = False
            deferred_menus: list[tuple[Any, list]] = []
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
                            deferred_menus.append((fx_file, records))
                            continue

                        await _apply_doctype_fixture(fx_doctype, records, session, eng)
                        logger.info("startup.fixture_applied", app=app_name, file=fx_file.name)
                    except Exception as e:
                        logger.warning(
                            "startup.fixture_failed", app=app_name, file=fx_file.name, error=str(e)
                        )

            for fx_file, records in deferred_menus:
                try:
                    workspace_from_fixture = await _apply_workspace_fixture(
                        records, app_name, app_meta
                    )
                    logger.info("startup.fixture_applied", app=app_name, file=fx_file.name)
                except Exception as e:
                    logger.warning(
                        "startup.fixture_failed", app=app_name, file=fx_file.name, error=str(e)
                    )

            # Auto-register PrintFormats from app's module print_formats directories.
            # Formats flagged is_app_format=true treat the file as the source of
            # truth: re-sync overwrites the DB template from disk every migrate
            # (mirrors the after_save hook that writes DB -> disk for the same flag).
            # Formats without the flag (created via the UI) stay skip-if-exists so
            # manual in-app edits are never clobbered by a migrate.
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

                        pf_name = data.get("name")
                        if data.get("is_app_format") and pf_name:
                            async with grunt.system_context(session, eng):
                                exists = await grunt.exists("PrintFormat", {"name": pf_name})
                                if exists:
                                    await grunt.db.set_value(
                                        "PrintFormat",
                                        str(pf_name),
                                        {
                                            "template": data.get("template", ""),
                                            "template_type": data.get("template_type", "html"),
                                            "is_default": bool(data.get("is_default", False)),
                                        },
                                    )
                            if exists:
                                await session.commit()
                                logger.info(
                                    "startup.print_format_synced", app=app_name, name=pf_name
                                )
                                continue

                        await _apply_doctype_fixture("PrintFormat", [data], session, eng)
                        logger.info(
                            "startup.print_format_registered", app=app_name, name=data.get("name")
                        )
                    except Exception as e:
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
                        import importlib.util

                        spec = importlib.util.spec_from_file_location(
                            f"{app_name}.install", install_module_path
                        )
                        if spec and spec.loader:
                            install_mod = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(install_mod)
                            if hasattr(install_mod, "after_install"):
                                await install_mod.after_install(session, site_name)
                                logger.info("startup.after_install_ok", app=app_name)
                    except Exception as e:
                        logger.warning("startup.after_install_failed", app=app_name, error=str(e))

            logger.info("startup.app_workspace_seeded", app=app_name)
