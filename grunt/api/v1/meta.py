"""Meta whitelisted methods for DocType management."""

from typing import Any

import sqlalchemy as sa

import grunt
from grunt import _, log
from grunt.actions import enrich_doctype_actions
from grunt.db.dialects import dialect_for
from grunt.document.validators import list_validators as _list
from grunt.errors import not_found
from grunt.metadata.compiler import DuplicateDataError, get_table_name, sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.dynamic_options import get_option_labels, get_schemas, resolve_field_options
from grunt.metadata.registry import doctype_registry
from grunt.metadata.scaffold import export_doctype_files
from grunt.workflow.registry import get_active_workflow
lazy from grunt.i18n.meta import translate_doctype_meta


async def _dump_doctype(dt: DocType, *, translate: bool = False) -> dict[str, Any]:
    """Serialize a DocType, resolving registry-backed options and field schemas.

    Fields with `options_source` set draw their choices from the dynamic
    options registry instead of the static `options` string. Fields with
    `dynamic_schema_source` set get every registered {key: fields} variant
    attached as `dynamic_schemas`, so the frontend can render the variant
    matching a sibling field's value (e.g. WebPageBlock.settings picking its
    form based on block_type) without a second round-trip.

    `workflow_state_field` is resolved from the active `Workflow` document (if
    any) rather than stored on the DocType itself - see grunt/workflow/registry.py.

    ``translate=True`` runs labels/descriptions/Select options through the i18n
    layer for the current request language (see grunt.i18n.meta). Only the
    presentational render paths pass it - never file export / sync.
    """
    data = dt.model_dump()
    for field, fdata in zip(dt.fields, data["fields"], strict=True):
        if field.options_source:
            fdata["options"] = resolve_field_options(field)
            if labels := get_option_labels(field.options_source):
                fdata["option_labels"] = labels
        if field.dynamic_schema_source:
            fdata["dynamic_schemas"] = {
                key: [dict(sub) for sub in fields]
                for key, fields in get_schemas(field.dynamic_schema_source).items()
            }
    workflow = await get_active_workflow(dt.name)
    data["workflow_state_field"] = workflow.state_field if workflow else None
    if workflow and translate:
        # The form hides the state (shown in the sidebar) - it moves by the header's workflow
        # actions (grunt/workflow/guard.py); the builder (raw) keeps the source.
        for fdata in data["fields"]:
            if fdata.get("fieldname") == workflow.state_field:
                fdata["read_only"] = True

    # Enrich `actions` bindings with defaults from the code registry and attach
    # `_action_catalog` for the binding editor - see grunt.actions.

    enrich_doctype_actions(data)

    if translate:
        translate_doctype_meta(data)
        for fdata in data["fields"]:
            for variant in (fdata.get("dynamic_schemas") or {}).values():
                for sub in variant:
                    if sub.get("label"):
                        sub["label"] = _(sub["label"])

    return data


async def _get_app_name_for_module(module: str) -> str | None:
    """Return the installed app name that owns *module*, or None."""
    rows = await grunt.db.get_all("GruntInstalledApp", fields=["name", "modules"])
    for row in rows:
        if module in (row.get("modules") or []):
            return row["name"]
    return None


@grunt.whitelist()
async def get_doctype(name: str, raw: bool = False) -> dict[str, Any]:
    """Get a single DocType definition, always re-reading from DB.

    Labels/descriptions/Select options are translated for the request language
    unless ``raw`` is set (the DocType builder edits the untranslated source).
    """
    await doctype_registry.get(name)  # ensure it exists (raises 404 if not)
    fresh = await doctype_registry._lazy_load(name)
    if fresh is None:
        meta = await grunt.get_meta(name)
        if meta is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": name})
        fresh = meta.doc
    return await _dump_doctype(fresh, translate=not raw)


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


@grunt.whitelist(roles=["System Manager"])
async def save_doctype(doctype_data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a DocType. Admin only."""

    dt = DocType(**doctype_data)
    session = grunt.get_session()
    engine = grunt.get_engine()

    try:
        if await doctype_registry.get_or_none(dt.name) is not None:
            if doctype_data.get("__is_new"):
                grunt.throw(
                    _("DocType “%(doctype)s” already exists") % {"doctype": dt.name}, "CONFLICT"
                )
            await doctype_registry.update(dt, session, engine)
        else:
            await doctype_registry.register(dt, session, engine)
    except DuplicateDataError as exc:
        grunt.throw(str(exc), "DUPLICATE_DATA")

    app_name = await _get_app_name_for_module(dt.module or "")
    export_doctype_files(dt, app_name=app_name)

    return await _dump_doctype(dt)


@grunt.whitelist(roles=["System Manager"])
async def delete_doctype(name: str) -> bool:
    """Delete a DocType definition. Admin only."""

    await doctype_registry.delete(name, grunt.get_session())
    return True


@grunt.whitelist(roles=["System Manager"])
async def sync_doctype(name: str) -> dict[str, Any]:
    """Force sync a DocType's physical table. Admin only."""
    meta = await grunt.get_meta(name)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": name})
    dt = meta.doc
    session = grunt.get_session()
    engine = grunt.get_engine()

    try:
        await sync_table(dt, engine, session=session)
    except DuplicateDataError as exc:
        grunt.throw(str(exc), "DUPLICATE_DATA")
    return {"name": dt.name, "table_name": get_table_name(dt.module, dt.name)}


@grunt.whitelist(roles=["System Manager"])
async def compact_table(name: str) -> dict[str, Any]:
    """Compact a DocType's backing table and report how much space was freed.

    Admin only. Blocking maintenance - the command holds a heavy lock while it
    rewrites storage, so callers should confirm before invoking:

    * SQLite - ``VACUUM`` (rewrites the *entire* database file)
    * Postgres - ``VACUUM (FULL, ANALYZE) <table>`` (ACCESS EXCLUSIVE on the table)
    * MySQL - ``OPTIMIZE TABLE <table>``

    Runs on a dedicated AUTOCOMMIT connection since none of these may run
    inside a transaction. Returns before/after byte figures and ``freed_bytes``
    (clamped at 0 - a table can legitimately grow slightly after a rewrite).
    """

    dt = await grunt.get_meta(name)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": name})
    if dt.is_virtual:
        grunt.throw(_("A virtual DocType has no physical table"), "VALIDATION_ERROR")

    table_name = dt.table_name or get_table_name(dt.module or "", dt.name)
    engine = grunt.get_engine()
    backend = dialect_for(engine)
    dialect = engine.dialect.name  # as reported - "mariadb" stays "mariadb"
    scope = backend.compaction_scope

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
            grunt.throw(_("The table has not been created in the database yet"), "VALIDATION_ERROR")

        quoted = conn.dialect.identifier_preparer.quote(table_name)
        cmd = backend.compaction_command(quoted)

        before = backend.compaction_footprint(conn, table_name)
        conn.exec_driver_sql(cmd)
        after = backend.compaction_footprint(conn, table_name)

        result["command"] = cmd
        result["before_bytes"] = before
        result["after_bytes"] = after
        if before is not None and after is not None:
            result["freed_bytes"] = max(0, before - after)

    async with engine.connect() as aconn:
        aconn = await aconn.execution_options(isolation_level="AUTOCOMMIT")
        await aconn.run_sync(_run)

    log.info(
        "meta.compact_table",
        doctype=dt.name,
        table=table_name,
        dialect=dialect,
        freed_bytes=result["freed_bytes"],
    )
    return result


@grunt.whitelist(roles=["System Manager"])
async def table_info(name: str) -> dict[str, Any]:
    """Return physical storage info for a DocType's backing table. Admin only.

    Reports the physical table name, row count and on-disk size (table vs
    indexes) plus how much space a compaction could reclaim. Size figures are
    dialect-specific and best-effort: SQLite needs the ``dbstat`` virtual
    table (usually compiled in), PostgreSQL/MySQL read it from the catalog.
    When the backend can't report sizes, ``size_supported`` is False and the
    byte fields stay null.
    """

    dt = await grunt.get_meta(name)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": name})
    if dt.is_virtual:
        grunt.throw(_("A virtual DocType has no physical table"), "VALIDATION_ERROR")

    table_name = dt.table_name or get_table_name(dt.module or "", dt.name)
    engine = grunt.get_engine()
    backend = dialect_for(engine)
    dialect = engine.dialect.name  # as reported - "mariadb" stays "mariadb"

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
        "reclaim_scope": None,  # "table" | "database" - what a compaction would touch
        "size_supported": False,
    }

    def _collect(conn: sa.engine.Connection) -> None:
        if not conn.dialect.has_table(conn, table_name):
            return
        info["exists"] = True
        quoted = conn.dialect.identifier_preparer.quote(table_name)  # "t" / `t` on MySQL
        info["row_count"] = conn.execute(sa.text(f"SELECT COUNT(*) FROM {quoted}")).scalar()

        info.update(backend.table_storage(conn, table_name))

    async with engine.connect() as aconn:
        await aconn.run_sync(_collect)

    return info


@grunt.whitelist()
async def list_validators() -> list[dict[str, object]]:
    """Return all registered field validators for the Studio UI."""
    return _list()
