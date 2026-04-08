"""Pages API — register and list custom app pages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.db.session import get_engine, get_session
from grunt.core.document.service import DocumentService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser

router = APIRouter()


def get_doc_service(
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
) -> DocumentService:
    return DocumentService(session, engine)


_PAGE_FIELDS = [
    "id",
    "route",
    "title",
    "icon",
    "component",
    "app",
    "sidebar_section",
    "sidebar_order",
    "is_default_home",
]

_PAGE_UPDATABLE = {
    "title",
    "icon",
    "component",
    "app",
    "sidebar_section",
    "sidebar_order",
    "is_default_home",
}


@router.get("/")
async def list_pages(
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """List all registered custom pages."""
    result = await svc.list_documents(
        "Page",
        user,
        per_page=10000,
        sort_by="sidebar_order",
        sort_order="asc",
        fields=_PAGE_FIELDS,
    )
    return {"success": True, "data": result["data"]}


@router.post("/")
async def register_page(
    body: dict[str, Any],
    user: GruntUser = Depends(superadmin_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Register or update a custom page from an app."""
    route = (body.get("route") or "").strip()
    if not route:
        raise HTTPException(status_code=422, detail="route є обов'язковим")

    from grunt.app import grunt  # noqa: PLC0415

    tokens = grunt.set_context(session=svc.session, engine=svc.engine, user=user)
    try:
        page_id = await grunt.db.get_value("Page", {"route": route}, "id")
    finally:
        grunt.reset_context(tokens)

    update_data = {k: v for k, v in body.items() if k in _PAGE_UPDATABLE}

    if page_id:
        doc = await svc.update_document("Page", page_id, update_data, user)
    else:
        doc = await svc.create_document("Page", {"route": route, **update_data}, user)

    return {"success": True, "data": {"route": route, "title": doc.get("title", route)}}


@router.delete("/{route:path}")
async def delete_page(
    route: str,
    user: GruntUser = Depends(superadmin_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Remove a custom page registration."""
    full_route = f"/{route}"

    from grunt.app import grunt  # noqa: PLC0415

    tokens = grunt.set_context(session=svc.session, engine=svc.engine, user=user)
    try:
        page_id = await grunt.db.get_value("Page", {"route": full_route}, "id")
    finally:
        grunt.reset_context(tokens)

    if not page_id:
        raise HTTPException(status_code=404, detail="Сторінку не знайдено")

    await svc.delete_document("Page", page_id, user)
    return {"success": True, "message": "Сторінку видалено"}
