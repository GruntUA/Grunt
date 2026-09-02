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


async def _dump_doctype(dt: DocType) -> dict[str, Any]:
    """Serialize a DocType, resolving registry-backed options and field schemas.

    Fields with `options_source` set draw their choices from the dynamic
    options registry instead of the static `options` string. Fields with
    `dynamic_schema_source` set get every registered {key: fields} variant
    attached as `dynamic_schemas`, so the frontend can render the variant
    matching a sibling field's value (e.g. WebPageBlock.settings picking its
    form based on block_type) without a second round-trip.

    `workflow_state_field` is resolved from the active `Workflow` document (if
    any) rather than stored on the DocType itself — see grunt/workflow/registry.py.
    """
    from grunt.workflow.registry import get_active_workflow

    data = dt.model_dump()
    for field, fdata in zip(dt.fields, data["fields"], strict=True):
        if field.options_source:
            fdata["options"] = resolve_field_options(field)
        if field.dynamic_schema_source:
            fdata["dynamic_schemas"] = get_schemas(field.dynamic_schema_source)
    workflow = await get_active_workflow(dt.name)
    data["workflow_state_field"] = workflow.state_field if workflow else None

    # Enrich `actions` bindings with defaults from the code registry and attach
    # `_action_catalog` for the binding editor — see grunt.actions.
    from grunt.actions import enrich_doctype_actions

    enrich_doctype_actions(data)
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
    return await _dump_doctype(fresh)


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

    return await _dump_doctype(dt)


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


def _compaction_footprint_bytes(conn: Any, table_name: str, dialect: str) -> int | None:
    """Bytes that a compaction of *table_name* can shrink, measured before/after.

    Matches the scope of the command ``compact_table`` runs for each dialect:
    the whole database file for SQLite (``VACUUM`` is file-wide), the single
    relation for PostgreSQL/MySQL. Returns None when the dialect is unknown.
    """
    import sqlalchemy as sa

    if dialect == "sqlite":
        page_count = int(conn.execute(sa.text("PRAGMA page_count")).scalar() or 0)
        page_size = int(conn.execute(sa.text("PRAGMA page_size")).scalar() or 0)
        return page_count * page_size
    if dialect == "postgresql":
        return int(
            conn.execute(
                sa.text("SELECT pg_total_relation_size(:t)"), {"t": table_name}
            ).scalar()
            or 0
        )
    if dialect in ("mysql", "mariadb"):
        row = conn.execute(
            sa.text(
                "SELECT data_length, index_length FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = :t"
            ),
            {"t": table_name},
        ).first()
        if row:
            return int((row[0] or 0) + (row[1] or 0))
        return 0
    return None


@grunt.whitelist(roles=["superadmin"])
async def compact_table(name: str) -> dict[str, Any]:
    """Compact a DocType's backing table and report how much space was freed.

    Admin only. Blocking maintenance — the command holds a heavy lock while it
    rewrites storage, so callers should confirm before invoking:

    * SQLite   — ``VACUUM`` (rewrites the *entire* database file)
    * Postgres — ``VACUUM (FULL, ANALYZE) <table>`` (ACCESS EXCLUSIVE on the table)
    * MySQL    — ``OPTIMIZE TABLE <table>``

    Runs on a dedicated AUTOCOMMIT connection since none of these may run
    inside a transaction. Returns before/after byte figures and ``freed_bytes``
    (clamped at 0 — a table can legitimately grow slightly after a rewrite).
    """
    import sqlalchemy as sa

    from grunt.app import grunt as grunt_app

    dt = await doctype_registry.get(name)
    if dt.is_virtual:
        grunt.throw("Віртуальний тип документа не має фізичної таблиці", "VALIDATION_ERROR")

    table_name = dt.table_name or get_table_name(dt.module or "", dt.name)
    engine = grunt_app._require_engine()
    dialect = engine.dialect.name

    if dialect == "sqlite":
        command, scope = "VACUUM", "database"
    elif dialect == "postgresql":
        scope = "table"
        command = None  # built below with a properly quoted identifier
    elif dialect in ("mysql", "mariadb"):
        scope = "table"
        command = None
    else:
        grunt.throw(f"Стиснення не підтримується для СКБД «{dialect}»", "VALIDATION_ERROR")

    result: dict[str, Any] = {
        "doctype": dt.name,
        "table_name": table_name,
        "dialect": dialect,
        "scope": scope,
        "before_bytes": None,
        "after_bytes": None,
        "freed_bytes": None,
    }

    def _run(conn: sa.engine.Connection) -> None:
        if not conn.dialect.has_table(conn, table_name):
            grunt.throw("Таблиця ще не створена в базі даних", "VALIDATION_ERROR")

        quoted = conn.dialect.identifier_preparer.quote(table_name)
        cmd = command
        if cmd is None:
            cmd = (
                f"VACUUM (FULL, ANALYZE) {quoted}"
                if dialect == "postgresql"
                else f"OPTIMIZE TABLE {quoted}"
            )

        before = _compaction_footprint_bytes(conn, table_name, dialect)
        conn.exec_driver_sql(cmd)
        after = _compaction_footprint_bytes(conn, table_name, dialect)

        result["command"] = cmd
        result["before_bytes"] = before
        result["after_bytes"] = after
        if before is not None and after is not None:
            result["freed_bytes"] = max(0, before - after)

    async with engine.connect() as aconn:
        aconn = await aconn.execution_options(isolation_level="AUTOCOMMIT")
        await aconn.run_sync(_run)

    logger.info(
        "meta.compact_table",
        doctype=dt.name,
        table=table_name,
        dialect=dialect,
        freed_bytes=result["freed_bytes"],
    )
    return result


@grunt.whitelist(roles=["superadmin"])
async def table_info(name: str) -> dict[str, Any]:
    """Return physical storage info for a DocType's backing table. Admin only.

    Reports the physical table name, row count and on-disk size (table vs
    indexes) plus how much space a compaction could reclaim. Size figures are
    dialect-specific and best-effort: SQLite needs the ``dbstat`` virtual
    table (usually compiled in), PostgreSQL/MySQL read it from the catalog.
    When the backend can't report sizes, ``size_supported`` is False and the
    byte fields stay null.
    """
    import sqlalchemy as sa

    from grunt.app import grunt as grunt_app

    dt = await doctype_registry.get(name)
    if dt.is_virtual:
        grunt.throw("Віртуальний тип документа не має фізичної таблиці", "VALIDATION_ERROR")

    table_name = dt.table_name or get_table_name(dt.module or "", dt.name)
    engine = grunt_app._require_engine()
    dialect = engine.dialect.name

    info: dict[str, Any] = {
        "doctype": dt.name,
        "table_name": table_name,
        "dialect": dialect,
        "exists": False,
        "row_count": None,
        "table_bytes": None,
        "index_bytes": None,
        "total_bytes": None,
        "reclaimable_bytes": None,
        "reclaim_scope": None,  # "table" | "database" — what a compaction would touch
        "size_supported": False,
    }

    def _collect(conn: sa.engine.Connection) -> None:
        if not conn.dialect.has_table(conn, table_name):
            return
        info["exists"] = True
        info["row_count"] = conn.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table_name}"')
        ).scalar()

        if dialect == "sqlite":
            try:
                page_size = int(conn.execute(sa.text("PRAGMA page_size")).scalar() or 0)
                idx_names = [
                    r[0]
                    for r in conn.execute(
                        sa.text(
                            "SELECT name FROM sqlite_master "
                            "WHERE type = 'index' AND tbl_name = :t"
                        ),
                        {"t": table_name},
                    )
                ]
                rows = conn.execute(
                    sa.text(
                        "SELECT name, SUM(pgsize) FROM dbstat "
                        "WHERE name IN :names GROUP BY name"
                    ).bindparams(sa.bindparam("names", expanding=True)),
                    {"names": [table_name, *idx_names]},
                ).all()
                by_name = {r[0]: int(r[1] or 0) for r in rows}
                tbytes = by_name.get(table_name, 0)
                ibytes = sum(by_name.get(n, 0) for n in idx_names)
                info["table_bytes"] = tbytes
                info["index_bytes"] = ibytes
                info["total_bytes"] = tbytes + ibytes
                info["size_supported"] = True
                # SQLite VACUUM works on the whole database file, not one table.
                freelist = int(conn.execute(sa.text("PRAGMA freelist_count")).scalar() or 0)
                info["reclaimable_bytes"] = freelist * page_size
                info["reclaim_scope"] = "database"
            except Exception:
                logger.debug("table_info.dbstat_unavailable", table=table_name)
        elif dialect == "postgresql":
            row = conn.execute(
                sa.text(
                    "SELECT pg_table_size(:t), pg_indexes_size(:t), "
                    "pg_total_relation_size(:t)"
                ),
                {"t": table_name},
            ).one()
            info["table_bytes"] = int(row[0])
            info["index_bytes"] = int(row[1])
            info["total_bytes"] = int(row[2])
            info["size_supported"] = True
            dead = conn.execute(
                sa.text("SELECT n_dead_tup FROM pg_stat_user_tables WHERE relname = :t"),
                {"t": table_name},
            ).scalar()
            info["dead_tuples"] = int(dead or 0)
            info["reclaim_scope"] = "table"
        elif dialect in ("mysql", "mariadb"):
            row = conn.execute(
                sa.text(
                    "SELECT data_length, index_length, data_free "
                    "FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = :t"
                ),
                {"t": table_name},
            ).first()
            if row:
                info["table_bytes"] = int(row[0] or 0)
                info["index_bytes"] = int(row[1] or 0)
                info["total_bytes"] = int((row[0] or 0) + (row[1] or 0))
                info["reclaimable_bytes"] = int(row[2] or 0)
                info["reclaim_scope"] = "table"
                info["size_supported"] = True

    async with engine.connect() as aconn:
        await aconn.run_sync(_collect)

    return info


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

    return {dt.name: await _dump_doctype(dt) for dt in all_dts}


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
