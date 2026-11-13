"""Meta whitelisted methods for DocType management."""

from typing import Any

import sqlalchemy as sa

from grunt.actions import enrich_doctype_actions
from grunt.api.context import whitelist
from grunt.db.api import GruntDB
from grunt.db.dialects import dialect_for
from grunt.db.schema.apply import DuplicateDataError
from grunt.document.validators import list_validators as _list
from grunt.errors import not_found, throw
from grunt.i18n import _
from grunt.local import require_engine, require_session
from grunt.log import log
from grunt.metadata.compiler import get_table_name, sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.dump import dump_doctype
from grunt.metadata.registry import doctype_registry
from grunt.metadata.scaffold import export_doctype_files

_db = GruntDB()  # stateless: reads through the context's session


async def _dump_doctype(dt: DocType, *, translate: bool = False) -> dict[str, Any]:
    """:func:`dump_doctype` with the ``actions`` bindings enriched from the code
    registry and ``_action_catalog`` attached for the binding editor - see grunt.actions."""
    data = await dump_doctype(dt, translate=translate)
    enrich_doctype_actions(data)
    return data


async def _get_app_name_for_module(module: str) -> str | None:
    """Return the installed app name that owns *module*, or None."""
    rows = await _db.get_all("GruntInstalledApp", fields=["name", "modules"])
    for row in rows:
        if module in (row.get("modules") or []):
            return row["name"]
    return None


@whitelist()
async def get_doctype(name: str, raw: bool = False) -> dict[str, Any]:
    """Get a single DocType definition, always re-reading from DB.

    Labels/descriptions/Select options are translated for the request language
    unless ``raw`` is set (the DocType builder edits the untranslated source).
    """
    await doctype_registry.get(name)  # ensure it exists (raises 404 if not)
    fresh = await doctype_registry._lazy_load(name)
    if fresh is None:
        meta = await doctype_registry.get_meta(name)
        if meta is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": name})
        fresh = meta.doc
    return await _dump_doctype(fresh, translate=not raw)


@whitelist()
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


@whitelist(perm="grunt.manage_doctypes")
async def save_doctype(doctype_data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a DocType. Admin only."""

    dt = DocType(**doctype_data)
    session = require_session()
    engine = require_engine()

    try:
        if await doctype_registry.get_or_none(dt.name) is not None:
            if doctype_data.get("__is_new"):
                throw(_("DocType “%(doctype)s” already exists") % {"doctype": dt.name}, "CONFLICT")
            await doctype_registry.update(dt, session, engine)
        else:
            await doctype_registry.register(dt, session, engine)
    except DuplicateDataError as exc:
        throw(str(exc), "DUPLICATE_DATA")

    app_name = await _get_app_name_for_module(dt.module or "")
    export_doctype_files(dt, app_name=app_name)

    return await _dump_doctype(dt)


@whitelist(perm="grunt.manage_doctypes")
async def delete_doctype(name: str) -> bool:
    """Delete a DocType definition. Admin only."""

    await doctype_registry.delete(name, require_session())
    return True


@whitelist(perm="grunt.manage_doctypes")
async def sync_doctype(name: str) -> dict[str, Any]:
    """Force sync a DocType's physical table. Admin only."""
    meta = await doctype_registry.get_meta(name)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": name})
    dt = meta.doc
    session = require_session()
    engine = require_engine()

    try:
        await sync_table(dt, engine, session=session)
    except DuplicateDataError as exc:
        throw(str(exc), "DUPLICATE_DATA")
    return {"name": dt.name, "table_name": get_table_name(dt.module, dt.name)}


@whitelist(perm="grunt.manage_doctypes")
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

    dt = await doctype_registry.get_meta(name)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": name})
    if not dt.has_table:
        throw(_("A virtual DocType has no physical table"), "VALIDATION_ERROR")

    table_name = dt.table_name or get_table_name(dt.module or "", dt.name)
    engine = require_engine()
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
            throw(_("The table has not been created in the database yet"), "VALIDATION_ERROR")

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


@whitelist(perm="grunt.manage_doctypes")
async def table_info(name: str) -> dict[str, Any]:
    """Return physical storage info for a DocType's backing table. Admin only.

    Reports the physical table name, row count and on-disk size (table vs
    indexes) plus how much space a compaction could reclaim. Size figures are
    dialect-specific and best-effort: SQLite needs the ``dbstat`` virtual
    table (usually compiled in), PostgreSQL/MySQL read it from the catalog.
    When the backend can't report sizes, ``size_supported`` is False and the
    byte fields stay null.
    """

    dt = await doctype_registry.get_meta(name)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": name})
    if not dt.has_table:
        throw(_("A virtual DocType has no physical table"), "VALIDATION_ERROR")

    table_name = dt.table_name or get_table_name(dt.module or "", dt.name)
    engine = require_engine()
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


@whitelist()
async def list_validators() -> list[dict[str, object]]:
    """Return all registered field validators for the Studio UI."""
    return _list()
