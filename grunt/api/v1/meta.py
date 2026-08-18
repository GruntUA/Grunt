"""Meta whitelisted methods for DocType management."""

from __future__ import annotations

from typing import Any

import structlog

import grunt
from grunt.metadata.compiler import DuplicateDataError, get_table_name, sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.dynamic_options import get_schemas, resolve_field_options
from grunt.metadata.registry import doctype_registry
from grunt.metadata.scaffold import export_doctype_files

logger = structlog.get_logger()


def _dump_doctype(dt: DocType) -> dict[str, Any]:
    """Serialize a DocType, resolving registry-backed options and field schemas.

    Fields with `options_source` set draw their choices from the dynamic
    options registry instead of the static `options` string. Fields with
    `dynamic_schema_source` set get every registered {key: fields} variant
    attached as `dynamic_schemas`, so the frontend can render the variant
    matching a sibling field's value (e.g. WebPageBlock.settings picking its
    form based on block_type) without a second round-trip.
    """
    data = dt.model_dump()
    for field, fdata in zip(dt.fields, data["fields"], strict=True):
        if field.options_source:
            fdata["options"] = resolve_field_options(field)
        if field.dynamic_schema_source:
            fdata["dynamic_schemas"] = get_schemas(field.dynamic_schema_source)
    return data


async def _get_app_name_for_module(module: str) -> str | None:
    """Return the installed app name that owns *module*, or None."""
    rows = await grunt.db.get_all("GruntInstalledApp", fields=["name", "modules"])
    for row in rows:
        if module in (row.get("modules") or []):
            return row["name"]
    return None


@grunt.whitelist()
async def get_doctype(name: str) -> dict[str, Any]:
    """Get a single DocType definition, always re-reading from DB."""
    await doctype_registry.get(name)  # ensure it exists (raises 404 if not)
    fresh = await doctype_registry._lazy_load(name)
    if fresh is None:
        fresh = await doctype_registry.get(name)
    return _dump_doctype(fresh)


@grunt.whitelist()
async def list_doctypes(module: str | None = None) -> list[dict[str, Any]]:
    """List all registered DocTypes."""
    all_dt = await doctype_registry.list_all()
    if module:
        all_dt = [dt for dt in all_dt if dt.module == module]
    return [
        {
            "name": dt.name,
            "label": dt.label,
            "module": dt.module,
            "is_child": dt.is_child,
            "is_singleton": dt.is_singleton,
        }
        for dt in all_dt
        if dt.name
    ]


@grunt.whitelist(roles=["superadmin"])
async def save_doctype(doctype_data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a DocType. Admin only."""
    from grunt.app import grunt as grunt_app

    dt = DocType(**doctype_data)
    session = grunt_app._require_session()
    engine = grunt_app._require_engine()

    try:
        if dt.name in doctype_registry._doctypes:
            if doctype_data.get("__is_new"):
                grunt.throw(f"DocType '{dt.name}' already exists", "CONFLICT")
            await doctype_registry.update(dt, session, engine)
        else:
            await doctype_registry.register(dt, session, engine)
    except DuplicateDataError as exc:
        grunt.throw(str(exc), "DUPLICATE_DATA")

    app_name = await _get_app_name_for_module(dt.module or "")
    export_doctype_files(dt, app_name=app_name)

    return _dump_doctype(dt)


@grunt.whitelist(roles=["superadmin"])
async def delete_doctype(name: str) -> bool:
    """Delete a DocType definition. Admin only."""
    from grunt.app import grunt as grunt_app

    await doctype_registry.delete(name, grunt_app._require_session())
    return True


@grunt.whitelist(roles=["superadmin"])
async def sync_doctype(name: str) -> dict[str, Any]:
    """Force sync a DocType's physical table. Admin only."""
    from grunt.app import grunt as grunt_app

    dt = await doctype_registry.get(name)
    session = grunt_app._require_session()
    engine = grunt_app._require_engine()

    try:
        await sync_table(dt, engine, session=session)
    except DuplicateDataError as exc:
        grunt.throw(str(exc), "DUPLICATE_DATA")
    return {"name": dt.name, "table_name": get_table_name(dt.module, dt.name)}


@grunt.whitelist()
async def search_meta(q: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search DocTypes and Reports by name/label."""
    q_lower = q.lower()
    results: list[dict[str, Any]] = []
    all_dts = await doctype_registry.list_all()
    for dt in all_dts:
        if dt.is_child or dt.is_virtual:
            continue
        if q_lower in dt.name.lower() or q_lower in (dt.label or "").lower():
            results.append(
                {
                    "doctype": "DocType",
                    "name": dt.name,
                    "display_title": dt.label or dt.name,
                    "module": dt.module or "",
                }
            )
    try:
        reports = await grunt.db.get_all(
            "Report", filters={"name": ["like", f"%{q}%"]}, fields=["name"], limit=int(limit)
        )
        for r in reports:
            results.append({"doctype": "Report", "name": r["name"], "display_title": r["name"]})
    except Exception:
        logger.exception("suppressed_error")
    return results[: int(limit)]


@grunt.whitelist()
async def export_schemas(
    names: list[str] | None = None, module: str | None = None
) -> dict[str, Any]:
    """Export DocType definitions (schemas) for frontend or sync."""
    all_dts = await doctype_registry.list_all()

    if names:
        all_dts = [dt for dt in all_dts if dt.name in names]

    if module:
        all_dts = [dt for dt in all_dts if dt.module == module]

    return {dt.name: _dump_doctype(dt) for dt in all_dts}


@grunt.whitelist()
async def list_validators() -> list[dict[str, object]]:
    """Return all registered field validators for the Studio UI."""
    from grunt.document.validators import list_validators as _list

    return _list()


@grunt.whitelist(roles=["superadmin"])
async def fix_link_uuids(doctype: str | None = None) -> dict[str, Any]:
    """Repair Link field values that still contain old UUID strings.

    After the id→name migration, Link fields may store the old UUID (id) of
    the target document instead of its name.  This scans every Link field,
    finds rows where the stored value matches an existing target document's
    ``id`` column, and replaces it with the correct ``name``.

    Pass *doctype* to limit the repair to a single DocType; omit to fix all.
    Superadmin only.
    """
    import sqlalchemy as sa

    from grunt.metadata.compiler import get_table_name
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import site_manager

    engine = site_manager.get_engine(site_manager.get_active_site())
    all_dts = await doctype_registry.list_all()
    if doctype:
        all_dts = [dt for dt in all_dts if dt.name == doctype]

    updated_total = 0
    report: list[dict[str, Any]] = []

    # Build a doctype_name → table_name map from the registry
    dt_table_map = {}
    for dt in all_dts:
        if dt.table_name:
            dt_table_map[dt.name] = dt.table_name
        elif dt.module:
            dt_table_map[dt.name] = get_table_name(dt.module, dt.name)

    def _fix_all(conn: sa.engine.Connection) -> None:
        nonlocal updated_total

        def _col_exists(table: str, col: str) -> bool:
            rows = conn.execute(sa.text(f'PRAGMA table_info("{table}")')).fetchall()
            return any(r[1] == col for r in rows)

        def _table_exists(table: str) -> bool:
            return conn.dialect.has_table(conn, table)

        for dt in all_dts:
            source_table = dt_table_map.get(dt.name)
            if not source_table or not _table_exists(source_table):
                continue

            count = 0
            for field in dt.fields:
                if field.fieldtype != "Link" or not field.options:
                    continue
                fieldname = field.fieldname
                target_table = dt_table_map.get(field.options)
                if not target_table or not _table_exists(target_table):
                    continue
                if not _col_exists(target_table, "id"):
                    continue  # target already migrated
                if not _col_exists(source_table, fieldname):
                    continue

                result = conn.execute(
                    sa.text(
                        f'UPDATE "{source_table}" '
                        f'SET "{fieldname}" = ('
                        f'  SELECT t.name FROM "{target_table}" t'
                        f'  WHERE t.id = "{source_table}"."{fieldname}"'
                        f") "
                        f'WHERE "{fieldname}" IN (SELECT id FROM "{target_table}")'
                    )
                )
                n = result.rowcount or 0
                if n:
                    count += n
                    logger.info(
                        "fix_link_uuids.fixed",
                        doctype=dt.name,
                        field=fieldname,
                        rows=n,
                    )

            if count:
                updated_total += count
                report.append({"doctype": dt.name, "rows_fixed": count})

        conn.commit()

    async with engine.connect() as aconn:
        await aconn.run_sync(_fix_all)

    logger.info("fix_link_uuids.done", total=updated_total)
    return {"total_rows_fixed": updated_total, "details": report}


@grunt.whitelist(roles=["superadmin"])
async def clear_cache() -> bool:
    """Clear metadata cache. Admin only."""
    doctype_registry.clear_cache()
    # Also invalidate permission cache
    from grunt.permissions.rbac import invalidate_permission_cache

    invalidate_permission_cache()
    return True
