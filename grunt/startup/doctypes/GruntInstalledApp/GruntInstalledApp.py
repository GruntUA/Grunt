from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import structlog

import grunt
from grunt.app import grunt as grunt_app
from grunt.document.base import Document

logger = structlog.get_logger(__name__)


class GruntInstalledApp(Document):
    """GruntInstalledApp DocType controller."""

    async def after_delete(self) -> None:
        """Called automatically after the App document is deleted from the DB."""
        name = self.get("name")
        if not name:
            return

        # Refuse to physically delete core framework
        if name == "grunt":
            logger.warning(
                "Attempted to delete core 'grunt' app files from disk, blocked by safety check."
            )
            return

        apps_dir = Path(grunt.__file__).resolve().parents[3]
        app_path = apps_dir / name

        if app_path.exists() and app_path.is_dir():
            shutil.rmtree(app_path)
            logger.info(f"Physically deleted app files for '{name}' at {app_path}")

        # Clean up associated Workspaces
        workspaces = await grunt_app.get_list("AppMenu", filters={"app": name})
        for ws in workspaces:
            try:
                await grunt_app.delete_doc("AppMenu", ws["name"])
                logger.info(f"Deleted workspace {ws['name']} associated with app {name}")
            except Exception as e:
                logger.error(f"Failed to delete workspace {ws['name']}: {e}")


@grunt.whitelist()
async def list_apps() -> list[dict[str, Any]]:
    """List all installed apps."""
    apps = await grunt_app.get_list("GruntInstalledApp")
    return [
        {
            "name": str(a.get("name")),
            "name": a.get("name"),
            "title": a.get("title"),
            "version": a.get("version", "0.1.0"),
            "modules": a.get("modules", []),
            "installed_at": str(a.get("installed_at")) if a.get("installed_at") else None,
        }
        for a in apps
    ]


@grunt.whitelist()
async def register_app(
    name: str,
    title: str | None = None,
    version: str = "0.1.0",
    modules: list[str] | None = None,
) -> dict[str, Any]:
    """Register a new installed app. Superadmin only."""
    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt_app.throw("Not authorized", "PERMISSION_DENIED")

    if not name:
        grunt_app.throw("name є обов'язковим", "VALIDATION_ERROR")

    existing = await grunt_app.get_list("GruntInstalledApp", filters={"name": name})
    if existing:
        grunt_app.throw(f"Додаток '{name}' вже встановлено", "CONFLICT")

    app = await grunt_app.new_doc(
        "GruntInstalledApp",
        {
            "name": name,
            "title": title or name,
            "version": version,
            "modules": modules or [],
        },
    )
    return {"name": app.get("name"), "title": app.get("title")}


@grunt.whitelist()
async def add_module(name: str, module: str) -> dict[str, Any]:
    """Add a module to an installed app."""
    apps = await grunt_app.get_list("GruntInstalledApp", filters={"name": name})
    if not apps:
        grunt_app.throw(f"Додаток '{name}' не знайдено", "NOT_FOUND")

    app_id = apps[0]["name"]
    app = await grunt_app.get_doc("GruntInstalledApp", app_id)

    module_name = (module or "").strip()
    if not module_name:
        grunt_app.throw("module є обов'язковим", "VALIDATION_ERROR")

    current_modules = app.get("modules", [])
    if module_name in current_modules:
        grunt_app.throw(f"Модуль '{module_name}' вже існує", "CONFLICT")

    current_modules.append(module_name)
    await grunt_app.save_doc("GruntInstalledApp", app_id, {"modules": current_modules})

    return {"name": app.get("name"), "title": app.get("title"), "modules": current_modules}


@grunt.whitelist()
async def delete_app(name: str) -> bool:
    """Uninstall an app. Superadmin only."""
    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt_app.throw("Not authorized", "PERMISSION_DENIED")

    apps = await grunt_app.get_list("GruntInstalledApp", filters={"name": name})
    if not apps:
        grunt_app.throw(f"Додаток '{name}' не знайдено", "NOT_FOUND")

    await grunt_app.delete_doc("GruntInstalledApp", apps[0]["name"])
    return True
