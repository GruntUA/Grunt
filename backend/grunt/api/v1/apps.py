"""Apps API — list and manage installed Grunt apps."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.db.system_tables import GruntInstalledApp

router = APIRouter()


@router.get("/")
async def list_apps(
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(current_user),
) -> dict:
    """List all installed apps."""
    result = await session.execute(select(GruntInstalledApp))
    apps = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(a.id),
                "name": a.name,
                "title": a.title,
                "version": a.version,
                "modules": a.modules,
                "installed_at": a.installed_at.isoformat() if a.installed_at else None,
            }
            for a in apps
        ],
    }


@router.post("/")
async def register_app(
    body: dict,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Register a new installed app."""
    name = body.get("name", "")
    if not name:
        raise HTTPException(status_code=422, detail="name є обов'язковим")

    existing = await session.execute(
        select(GruntInstalledApp).where(GruntInstalledApp.name == name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Додаток '{name}' вже встановлено")

    app = GruntInstalledApp(
        name=name,
        title=body.get("title", name),
        version=body.get("version", "0.1.0"),
        modules=body.get("modules", []),
    )
    session.add(app)
    await session.flush()
    return {"success": True, "data": {"name": app.name, "title": app.title}}


@router.delete("/{name}")
async def delete_app(
    name: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Uninstall an app."""
    result = await session.execute(
        select(GruntInstalledApp).where(GruntInstalledApp.name == name)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Додаток '{name}' не знайдено")
    await session.delete(app)
    await session.flush()
    return {"success": True, "message": f"Додаток '{name}' видалено"}
