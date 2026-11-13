import shutil
from datetime import UTC, datetime
from typing import Any

from grunt.api.context import whitelist
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.log import log
from grunt.permissions.perms import has_perm
from grunt.site.bench import bench_dir
lazy from grunt.document.api import documents


class GruntInstalledApp(Document):
    """GruntInstalledApp DocType controller."""

    async def before_insert(self) -> None:
        if not self.data.get("installed_at"):
            self.data["installed_at"] = datetime.now(UTC)
        if self.data.get("modules") is None:
            self.data["modules"] = []

    async def after_delete(self) -> None:
        """Called automatically after the App document is deleted from the DB."""
        name = self.get("name")
        if not name:
            return

        # Refuse to physically delete core framework
        if name == "grunt":
            log.warning(
                "Attempted to delete core 'grunt' app files from disk, blocked by safety check."
            )
            return

        app_path = bench_dir() / "apps" / name

        if app_path.exists() and app_path.is_dir():
            shutil.rmtree(app_path)
            log.info(f"Physically deleted app files for '{name}' at {app_path}")

        # Clean up associated Workspaces
        workspaces = await documents.get_list("AppMenu", filters={"app": name})
        for ws in workspaces:
            try:
                await documents.delete_doc("AppMenu", ws["name"])
                log.info(f"Deleted workspace {ws['name']} associated with app {name}")
            except Exception as e:
                log.error(f"Failed to delete workspace {ws['name']}: {e}")


@whitelist()
async def list_apps() -> list[dict[str, Any]]:
    """List all installed apps."""
    apps = await documents.get_list("GruntInstalledApp")
    return [
        {
            "name": a.get("name"),
            "title": a.get("title"),
            "version": a.get("version", "0.1.0"),
            "modules": a.get("modules", []),
            "installed_at": str(a.get("installed_at")) if a.get("installed_at") else None,
        }
        for a in apps
    ]


@whitelist()
async def register_app(
    name: str,
    title: str | None = None,
    version: str = "0.1.0",
    modules: list[str] | None = None,
) -> dict[str, Any]:
    """Register a new installed app. Needs ``grunt.manage_apps``."""
    if not await has_perm("grunt.manage_apps"):
        throw(_("Not authorized"), "PERMISSION_DENIED")

    if not name:
        throw(_("name is required"), "VALIDATION_ERROR")

    existing = await documents.get_list("GruntInstalledApp", filters={"name": name})
    if existing:
        throw(_("App “%(app)s” is already installed") % {"app": name}, "CONFLICT")

    app = await documents.new_doc(
        "GruntInstalledApp",
        {
            "name": name,
            "title": title or name,
            "version": version,
            "modules": modules or [],
        },
    )
    return {"name": app.get("name"), "title": app.get("title")}


@whitelist()
async def add_module(name: str, module: str) -> dict[str, Any]:
    """Add a module to an installed app."""
    apps = await documents.get_list("GruntInstalledApp", filters={"name": name})
    if not apps:
        throw(_("App “%(app)s” not found") % {"app": name}, "NOT_FOUND")

    app_id = apps[0]["name"]
    app = await documents.get_doc(GruntInstalledApp, app_id)

    module_name = (module or "").strip()
    if not module_name:
        throw(_("module is required"), "VALIDATION_ERROR")

    current_modules = app.modules or []
    if module_name in current_modules:
        throw(_("Module “%(module)s” already exists") % {"module": module_name}, "CONFLICT")

    current_modules.append(module_name)
    await documents.save_doc("GruntInstalledApp", app_id, {"modules": current_modules})

    return {"name": app.name, "title": app.title, "modules": current_modules}


@whitelist()
async def delete_app(name: str) -> bool:
    """Uninstall an app. Needs ``grunt.manage_apps``."""
    if not await has_perm("grunt.manage_apps"):
        throw(_("Not authorized"), "PERMISSION_DENIED")

    apps = await documents.get_list("GruntInstalledApp", filters={"name": name})
    if not apps:
        throw(_("App “%(app)s” not found") % {"app": name}, "NOT_FOUND")

    await documents.delete_doc("GruntInstalledApp", apps[0]["name"])
    return True
