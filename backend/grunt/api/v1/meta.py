"""Meta API endpoints — DocType CRUD and sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import engine, get_session
from grunt.core.metadata.compiler import compile_doctype_to_table, get_table_name, sync_table
from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.registry import doctype_registry
from grunt.api.v1.schemas.meta import (
    DocTypeListItem,
    DocTypeSchema,
    DocTypeSyncResult,
)
from grunt.core.metadata.system_doctypes import is_system_doctype

from sqlalchemy import inspect as sa_inspect

router = APIRouter()


def _doctype_to_schema(dt: DocType) -> DocTypeSchema:
    return DocTypeSchema.model_validate(dt.model_dump())


async def _sync_doctype_doc(dt: DocType, session: AsyncSession, *, delete: bool = False) -> None:
    """Keep the DocType document table in sync after meta operations."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415
    from grunt.core.metadata.system_doctypes import SYSTEM_DOCTYPES  # noqa: PLC0415

    dt_def = SYSTEM_DOCTYPES.get("DocType")
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
    if module:
        all_dt = [dt for dt in all_dt if dt.module == module]
    return [
        DocTypeListItem(name=dt.name, label=dt.label, module=dt.module, is_child=dt.is_child)
        for dt in all_dt
    ]


@router.post("/doctypes", response_model=DocTypeSchema, status_code=status.HTTP_201_CREATED)
async def create_doctype(
    body: DocType,
    session: AsyncSession = Depends(get_session),
    _user: GruntUser = Depends(superadmin_user),
) -> DocTypeSchema:
    """Create a new DocType — validates, persists, syncs table."""
    await doctype_registry.register(body, session, engine)
    await _sync_doctype_doc(body, session)
    return _doctype_to_schema(body)


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
) -> DocTypeSchema:
    """Update an existing DocType."""
    if body.name != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DocType name in URL and body must match",
        )
    await doctype_registry.update(body, session, engine)
    await _sync_doctype_doc(body, session)
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

    await sync_table(dt, engine, session=session)

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
