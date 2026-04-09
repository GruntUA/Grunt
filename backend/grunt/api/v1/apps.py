"""Apps API — list and manage installed Grunt apps."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from grunt.api.router import GruntRouter
from grunt.app import grunt

router = GruntRouter(prefix="", tags=["apps"])


@router.get("/")
async def list_apps() -> dict[str, Any]:
    """List all installed apps."""
    apps = await grunt.get_list("GruntInstalledApp")
    return {
        "success": True,
        "data": [
            {
                "id": str(a.get("id")),
                "name": a.get("name"),
                "title": a.get("title"),
                "version": a.get("version", "0.1.0"),
                "modules": a.get("modules", []),
                "installed_at": str(a.get("installed_at")) if a.get("installed_at") else None,
            }
            for a in apps
        ],
    }


@router.post("/")
async def register_app(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Register a new installed app."""
    if not grunt.session.is_superadmin:
        raise HTTPException(status_code=403, detail="Not authorized")

    name = body.get("name", "")
    if not name:
        raise HTTPException(status_code=422, detail="name є обов'язковим")

    existing = await grunt.get_list("GruntInstalledApp", filters={"name": name})
    if existing:
        raise HTTPException(status_code=409, detail=f"Додаток '{name}' вже встановлено")

    app = await grunt.new_doc(
        "GruntInstalledApp",
        {
            "name": name,
            "title": body.get("title", name),
            "version": body.get("version", "0.1.0"),
            "modules": body.get("modules", []),
        },
    )
    return {"success": True, "data": {"name": app.get("name"), "title": app.get("title")}}


@router.post("/{name}/modules")
async def add_module(
    name: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Add a module to an installed app."""
    apps = await grunt.get_list("GruntInstalledApp", filters={"name": name})
    if not apps:
        raise HTTPException(status_code=404, detail=f"Додаток '{name}' не знайдено")

    app_id = apps[0]["id"]
    app = await grunt.get_doc("GruntInstalledApp", app_id)

    module_name = (body.get("module") or "").strip()
    if not module_name:
        raise HTTPException(status_code=422, detail="module є обов'язковим")

    current_modules = app.get("modules", [])
    if module_name in current_modules:
        raise HTTPException(status_code=409, detail=f"Модуль '{module_name}' вже існує")

    current_modules.append(module_name)
    await grunt.save_doc("GruntInstalledApp", app_id, {"modules": current_modules})

    return {
        "success": True,
        "data": {"name": app.get("name"), "title": app.get("title"), "modules": current_modules},
    }


@router.delete("/{name}")
async def delete_app(
    name: str,
) -> dict[str, Any]:
    """Uninstall an app."""
    if not grunt.session.is_superadmin:
        raise HTTPException(status_code=403, detail="Not authorized")

    apps = await grunt.get_list("GruntInstalledApp", filters={"name": name})
    if not apps:
        raise HTTPException(status_code=404, detail=f"Додаток '{name}' не знайдено")

    await grunt.delete_doc("GruntInstalledApp", apps[0]["id"])
    return {"success": True, "message": f"Додаток '{name}' видалено"}
