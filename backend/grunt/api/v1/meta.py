"""Meta API endpoints — DocType CRUD and sync."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import inspect as sa_inspect

from grunt.api.router import GruntRouter
from grunt.app import grunt
from grunt.api.v1.schemas.meta import (
    DocTypeListItem,
    DocTypeSaveResult,
    DocTypeSchema,
    DocTypeSyncResult,
    IndexHint,
)
from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.metadata.compiler import compile_doctype_to_table, get_table_name, sync_table
from grunt.core.metadata.registry import doctype_registry
from grunt.core.metadata.scaffold import export_doctype_files
from grunt.core.metadata.doctype import DocType
from grunt.core.auth.models import GruntUser

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()
router = GruntRouter(prefix="", tags=["meta"])


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


_NON_PHYSICAL = frozenset({"Section", "Column", "Tab", "Table", "MultiLink"})


def _get_index_hints(dt: DocType) -> list[IndexHint]:
    """Return index recommendations for fields that are likely to be queried."""
    hints = []
    for f in dt.fields:
        if f.fieldtype in _NON_PHYSICAL or f.hidden or f.unique or f.index:
            continue
        if f.in_filter:
            hints.append(
                IndexHint(
                    field=f.fieldname,
                    reason=(
                        f"Поле «{f.label or f.fieldname}» використовується у фільтрах "
                        "(in_filter: true) — рекомендується додати index: true"
                    ),
                )
            )
        elif f.fieldtype == "Link":
            hints.append(
                IndexHint(
                    field=f.fieldname,
                    reason=(
                        f"Link-поле «{f.label or f.fieldname}» часто фігурує у "
                        "WHERE-умовах — рекомендується додати index: true"
                    ),
                )
            )
    return hints


async def _sync_doctype_doc(dt: DocType, session: AsyncSession, *, delete: bool = False) -> None:
    """Keep the DocType document table in sync after meta operations."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime  # noqa: PLC0415

    dt_def = doctype_registry._doctypes.get("DocType")
    if not dt_def:
        return
    table = compile_doctype_to_table(dt_def)
    conn = await session.connection()
    now = datetime.now(UTC)

    if delete:
        await conn.execute(table.delete().where(table.c.name == dt.name))
        return

    # Upsert
    result = await conn.execute(table.select().where(table.c.name == dt.name))
    if result.first():
        await conn.execute(
            table.update()
            .where(table.c.name == dt.name)
            .values(
                label=dt.label,
                module=dt.module,
                is_child=dt.is_child,
                modified_at=now,
            )
        )
    else:
        await conn.execute(
            table.insert().values(
                id=str(_uuid.uuid4()),
                name=dt.name,
                label=dt.label,
                module=dt.module,
                is_child=dt.is_child,
                owner="system",
                created_at=now,
                modified_at=now,
                modified_by="system",
                docstatus=0,
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
        DocTypeListItem(
            name=dt.name,
            label=dt.label,
            module=dt.module,
            is_child=dt.is_child,
            is_singleton=dt.is_singleton,
        )
        for dt in all_dt
    ]


@router.post("/doctypes", status_code=status.HTTP_201_CREATED, response_model=DocTypeSaveResult)
async def create_doctype(
    body: DocType,
    _: GruntUser = Depends(superadmin_user),
) -> DocTypeSaveResult:
    """Create a new DocType — validates, persists, syncs table, exports files."""
    await doctype_registry.register(body, grunt._require_session(), grunt._require_engine())
    await _sync_doctype_doc(body, grunt._require_session())
    app_name = await _get_app_name_for_module(body.module or "", grunt._require_session())
    exported_to = export_doctype_files(body, app_name=app_name)
    return DocTypeSaveResult(
        data=_doctype_to_schema(body), hints=_get_index_hints(body), exported_to=exported_to
    )


@router.get("/doctypes/{name}")
async def get_doctype_meta(
    name: str,
    _user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Get a single DocType by name."""
    dt = await doctype_registry.get(name)
    return _doctype_to_schema(dt).model_dump()


@router.put("/doctypes/{name}", response_model=DocTypeSaveResult)
async def update_doctype(
    name: str,
    body: DocType,
    _: GruntUser = Depends(superadmin_user),
) -> DocTypeSaveResult:
    """Update an existing DocType."""
    if body.name != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DocType name in URL and body must match",
        )
    await doctype_registry.update(body, grunt._require_session(), grunt._require_engine())
    await _sync_doctype_doc(body, grunt._require_session())
    app_name = await _get_app_name_for_module(body.module or "", grunt._require_session())
    exported_to = export_doctype_files(body, app_name=app_name)
    return DocTypeSaveResult(
        data=_doctype_to_schema(body), hints=_get_index_hints(body), exported_to=exported_to
    )


@router.delete("/doctypes/{name}")
async def delete_doctype(
    name: str,
    _: GruntUser = Depends(superadmin_user),
) -> dict[str, str]:
    """Delete a DocType (table is NOT dropped)."""
    dt = await doctype_registry.get(name)
    await doctype_registry.delete(name, grunt._require_session())
    await _sync_doctype_doc(dt, grunt._require_session(), delete=True)
    return {"message": f"DocType '{name}' видалено"}


@router.post("/doctypes/{name}/sync", response_model=DocTypeSyncResult)
async def sync_doctype(
    name: str,
    _: GruntUser = Depends(superadmin_user),
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

    conn = await grunt._require_session().connection()
    columns_before = await conn.run_sync(_get_columns)

    await sync_table(dt, grunt._require_engine(), session=grunt._require_session())

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
    _: GruntUser = Depends(current_user),
) -> list[dict]:
    """Return all Role documents."""
    from grunt.app import grunt  # noqa: PLC0415
    roles = await grunt.db.get_all(
        "Role",
        fields=["role_name", "description"],
        order_by="role_name",
        order="asc",
        limit=1000,
    )
    return [{"name": r["role_name"], "description": r.get("description")} for r in roles]


@router.patch("/doctypes/{name}/permissions", response_model=DocTypeSchema)
async def patch_permissions(
    name: str,
    permissions: list[dict],
    _: GruntUser = Depends(superadmin_user),
) -> DocTypeSchema:
    """Patch only the permissions field of a DocType."""
    from grunt.app import grunt  # noqa: PLC0415
    dt = await doctype_registry.get(name)
    from grunt.core.metadata.doctype import DocTypePermission  # noqa: PLC0415

    dt_dict = dt.model_dump()
    dt_dict["permissions"] = [DocTypePermission(**p).model_dump() for p in permissions]
    updated = type(dt)(**dt_dict)
    await doctype_registry.update(updated, grunt._require_session(), grunt._require_engine())
    await _sync_doctype_doc(updated, grunt._require_session())
    app_name = await _get_app_name_for_module(updated.module or "", grunt._require_session())
    export_doctype_files(updated, app_name=app_name)
    return _doctype_to_schema(updated)


@router.get("/introspect/hooks")
async def introspect_hooks(
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """List all registered global hooks."""
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    return {
        "success": True,
        "data": {
            event: [
                {"doctype": dt, "fn": f.__name__, "priority": p}
                for dt, p, f in hooks
            ]
            for event, hooks in doctype_registry._hooks.items()
        }
    }


@router.get("/introspect/controllers")
async def introspect_controllers(
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """List all registered DocType controllers."""
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    return {
        "success": True,
        "data": {
            name: {"class": cls.__name__, "module": cls.__module__}
            for name, cls in doctype_registry._controllers.items()
        }
    }


@router.get("/export-schemas", response_model=dict[str, DocTypeSchema])
async def export_schemas(
    module: str | None = None,
    names: list[str] | None = Query(None),
    _: GruntUser = Depends(current_user),
) -> dict[str, DocTypeSchema]:
    """Bulk export DocType schemas for the frontend (TypeScript generation, etc)."""
    all_dt = await doctype_registry.list_all()

    if names:
        target_names = set(names)
        all_dt = [dt for dt in all_dt if dt.name in target_names]

    if module:
        all_dt = [dt for dt in all_dt if dt.module == module]

    return {dt.name: _doctype_to_schema(dt) for dt in all_dt if dt.name}
