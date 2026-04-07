"""Meta API endpoints — DocType CRUD and sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_engine, get_session
from grunt.core.metadata.compiler import compile_doctype_to_table, get_table_name, sync_table
from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.registry import doctype_registry
from grunt.core.metadata.scaffold import export_doctype_files
from grunt.api.v1.schemas.meta import (
    DocTypeListItem,
    DocTypeSchema,
    DocTypeSyncResult,
)

from sqlalchemy import inspect as sa_inspect

import structlog

logger = structlog.get_logger()
router = APIRouter()


async def _get_app_name_for_module(module: str, session: AsyncSession) -> str | None:
    """Return the installed app name that owns *module*, or None."""
    from sqlalchemy import select  # noqa: PLC0415
    from grunt.core.db.system_tables import GruntInstalledApp  # noqa: PLC0415

    result = await session.execute(select(GruntInstalledApp))
    for app in result.scalars().all():
        if module in (app.modules or []):
            return app.name
    return None


def _doctype_to_schema(dt: DocType) -> DocTypeSchema:
    return DocTypeSchema.model_validate(dt.model_dump())


async def _sync_doctype_doc(dt: DocType, session: AsyncSession, *, delete: bool = False) -> None:
    """Keep the DocType document table in sync after meta operations."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    dt_def = doctype_registry._doctypes.get("DocType")
    if not dt_def:
        return
    table = compile_doctype_to_table(dt_def)
    conn = await session.connection()
    now = datetime.now(timezone.utc)

    if delete:
        await conn.execute(table.delete().where(table.c.name == dt.name))
        return

    # Upsert
    result = await conn.execute(
        table.select().where(table.c.name == dt.name)
    )
    if result.first():
        await conn.execute(
            table.update().where(table.c.name == dt.name).values(
                label=dt.label, module=dt.module, is_child=dt.is_child,
                modified_at=now,
            )
        )
    else:
        await conn.execute(
            table.insert().values(
                id=str(_uuid.uuid4()), name=dt.name, label=dt.label,
                module=dt.module, is_child=dt.is_child,
                owner="system", created_at=now, modified_at=now,
                modified_by="system", docstatus=0,
            )
        )


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/doctypes", response_model=list[DocTypeListItem])
async def list_doctypes(
    module: str | None = None,
    _user: GruntUser = Depends(current_user),
) -> list[DocTypeListItem]:
    """List all registered DocTypes, optionally filtered by module."""
    all_dt = await doctype_registry.list_all()
    all_dt = [dt for dt in all_dt if dt.name]  # exclude unnamed (unsaved) doctypes
    if module:
        all_dt = [dt for dt in all_dt if dt.module == module]
    return [
        DocTypeListItem(name=dt.name, label=dt.label, module=dt.module, is_child=dt.is_child, is_singleton=dt.is_singleton)
        for dt in all_dt
    ]


@router.post("/doctypes", status_code=status.HTTP_201_CREATED)
async def create_doctype(
    body: DocType,
    session: AsyncSession = Depends(get_session),
    _user: GruntUser = Depends(superadmin_user),
    eng: AsyncEngine = Depends(get_engine),
) -> dict:
    """Create a new DocType — validates, persists, syncs table, exports files."""
    await doctype_registry.register(body, session, eng)
    await _sync_doctype_doc(body, session)
    app_name = await _get_app_name_for_module(body.module or "", session)
    export_doctype_files(body, app_name=app_name)
    return {"success": True, "data": _doctype_to_schema(body).model_dump()}


@router.get("/doctypes/{name}", response_model=DocTypeSchema)
async def get_doctype(
    name: str,
    _user: GruntUser = Depends(current_user),
) -> DocTypeSchema:
    """Get a single DocType by name."""
    dt = await doctype_registry.get(name)
    return _doctype_to_schema(dt)


@router.put("/doctypes/{name}", response_model=DocTypeSchema)
async def update_doctype(
    name: str,
    body: DocType,
    session: AsyncSession = Depends(get_session),
    _user: GruntUser = Depends(superadmin_user),
    eng: AsyncEngine = Depends(get_engine),
) -> DocTypeSchema:
    """Update an existing DocType."""
    if body.name != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DocType name in URL and body must match",
        )
    await doctype_registry.update(body, session, eng)
    await _sync_doctype_doc(body, session)
    app_name = await _get_app_name_for_module(body.module or "", session)
    export_doctype_files(body, app_name=app_name)
    return _doctype_to_schema(body)


@router.delete("/doctypes/{name}")
async def delete_doctype(
    name: str,
    session: AsyncSession = Depends(get_session),
    _user: GruntUser = Depends(superadmin_user),
) -> dict[str, str]:
    """Delete a DocType (table is NOT dropped)."""
    dt = await doctype_registry.get(name)
    await doctype_registry.delete(name, session)
    await _sync_doctype_doc(dt, session, delete=True)
    return {"message": f"DocType '{name}' видалено"}


@router.post("/doctypes/{name}/sync", response_model=DocTypeSyncResult)
async def sync_doctype(
    name: str,
    session: AsyncSession = Depends(get_session),
    _user: GruntUser = Depends(superadmin_user),
    eng: AsyncEngine = Depends(get_engine),
) -> DocTypeSyncResult:
    """Force-sync a DocType's physical table with its definition."""
    dt = await doctype_registry.get(name)
    table_name = get_table_name(dt.module, dt.name)

    # Capture columns before sync
    def _get_columns(connection):  # noqa: ANN001
        insp = sa_inspect(connection)
        if insp.has_table(table_name):
            return {c["name"] for c in insp.get_columns(table_name)}
        return set()

    conn = await session.connection()
    columns_before = await conn.run_sync(_get_columns)

    await sync_table(dt, eng, session=session)

    columns_after = await conn.run_sync(_get_columns)

    columns_added = sorted(columns_after - columns_before)

    return DocTypeSyncResult(
        name=dt.name,
        table_name=table_name,
        columns_added=columns_added,
        message=f"Синхронізовано: додано {len(columns_added)} колонок"
        if columns_added
        else "Таблиця актуальна, змін не потрібно",
    )


# ── RBAC helpers ──────────────────────────────────────────────────────────


@router.get("/roles")
async def list_roles(
    session: AsyncSession = Depends(get_session),
    _user: GruntUser = Depends(current_user),
) -> list[dict]:
    """Return all Role documents."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.auth.models import SYSTEM_USER  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        roles = await grunt.db.get_all(
            "Role", fields=["role_name", "description"], order_by="role_name", order="asc", limit=1000
        )
    finally:
        grunt.reset_context(_tokens)
    return [{"name": r["role_name"], "description": r.get("description")} for r in roles]


@router.patch("/doctypes/{name}/permissions", response_model=DocTypeSchema)
async def patch_permissions(
    name: str,
    permissions: list[dict],
    session: AsyncSession = Depends(get_session),
    _user: GruntUser = Depends(superadmin_user),
    eng: AsyncEngine = Depends(get_engine),
) -> DocTypeSchema:
    """Patch only the permissions field of a DocType."""
    dt = await doctype_registry.get(name)
    from grunt.core.metadata.doctype import DocTypePermission  # noqa: PLC0415
    dt_dict = dt.model_dump()
    dt_dict["permissions"] = [DocTypePermission(**p).model_dump() for p in permissions]
    updated = type(dt)(**dt_dict)
    await doctype_registry.update(updated, session, eng)
    await _sync_doctype_doc(updated, session)
    app_name = await _get_app_name_for_module(updated.module or "", session)
    export_doctype_files(updated, app_name=app_name)
    return _doctype_to_schema(updated)
