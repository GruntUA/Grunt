"""Startup — DocType registry bootstrap and population."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.metadata.compiler import compile_doctype_to_table

logger = structlog.get_logger()

_CORE_DOCTYPES_DIR = __import__("pathlib").Path(__file__).parent.parent / "doctypes"


async def apply_doctype_overrides(session: AsyncSession, engine: AsyncEngine) -> None:
    """Apply field extensions registered by apps via ``doctype_overrides`` in hooks.py.

    For each DocType listed in ``hooks.DOCTYPE_OVERRIDES``, new fields that are
    not yet present are appended to the in-memory DocType definition.

    Physical table changes (ALTER TABLE) are NOT applied here — run
    ``grunt migrate`` to synchronise DB schema with DocType definitions.

    Must be called after all DocTypes are loaded into the registry.
    """
    from grunt.core.hooks import DOCTYPE_OVERRIDES
    from grunt.core.metadata.field import DocField
    from grunt.core.metadata.registry import doctype_registry

    if not DOCTYPE_OVERRIDES:
        return

    for doctype_name, spec in DOCTYPE_OVERRIDES.items():
        dt = doctype_registry._doctypes.get(doctype_name)
        if dt is None:
            logger.warning("startup.override_doctype_not_found", doctype=doctype_name)
            continue

        existing_fieldnames = {f.fieldname for f in dt.fields}
        added: list[str] = []

        for field_def in spec.get("add_fields", []):
            fname = field_def.get("fieldname")
            if not fname or fname in existing_fieldnames:
                continue
            try:
                dt.fields.append(DocField(**field_def))
                existing_fieldnames.add(fname)
                added.append(fname)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "startup.override_field_invalid",
                    doctype=doctype_name,
                    field=fname,
                    error=str(e),
                )

        if added:
            logger.info(
                "startup.doctype_overrides_applied",
                doctype=doctype_name,
                added_fields=added,
            )


async def load_core_doctypes(session: AsyncSession, sync_db: bool = False) -> None:
    """Register DocTypes defined as JSON files in grunt/core/doctypes/.

    These are first-class framework DocTypes (DocType itself, Dashboard, etc.)
    that live in the grunt package rather than in external apps.
    Uses _inject_core to bypass user-facing validation.
    """
    import json  # noqa: PLC0415

    from grunt.core.metadata.doctype import DocType  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    if not _CORE_DOCTYPES_DIR.exists():
        return

    for dt_file in sorted(_CORE_DOCTYPES_DIR.glob("**/*.json")):
        try:
            dt_data = json.loads(dt_file.read_text(encoding="utf-8"))
            dt_name = dt_data.get("name", "")
            if not dt_name:
                continue
            dt_obj = DocType.model_validate(dt_data)
            await doctype_registry._inject_core(dt_obj, session, sync_db=sync_db)
            if sync_db:
                logger.info("startup.core_doctype_injected", doctype=dt_name)
        except Exception as e:  # noqa: BLE001
            logger.warning("startup.core_doctype_failed", file=dt_file.name, error=str(e))


async def populate_system_doctypes(
    session: AsyncSession,
    engine: AsyncEngine,
) -> None:
    """Ensure every registered DocType has a row in the ``DocType`` document table.

    This keeps the DocType list view in sync with the registry.
    """
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    dt_def = doctype_registry._doctypes.get("DocType")
    if dt_def is None:
        logger.warning("startup.doctype_def_missing")
        return
    if dt_def.is_virtual:
        logger.info("startup.doctype_table_sync_skipped", reason="virtual_doctype")
        return
    table = compile_doctype_to_table(dt_def)

    all_doctypes = await doctype_registry.list_all()

    conn = await session.connection()
    try:
        result = await conn.execute(select(table.c.name))
        existing_names = {row[0] for row in result}
    except Exception:
        existing_names = set()

    now = datetime.now(UTC)

    # Only include columns that actually exist in the compiled table to
    # avoid errors when the schema hasn't been migrated yet.
    col_names = {c.name for c in table.columns}

    def _col(name: str, value: object) -> dict:
        return {name: value} if name in col_names else {}

    for dt in all_doctypes:
        scalar_fields: dict = {
            **_col("label", dt.label),
            **_col("module", dt.module),
            **_col("is_child", dt.is_child),
            **_col("is_submittable", dt.is_submittable),
            **_col("is_singleton", dt.is_singleton),
            **_col("is_virtual", dt.is_virtual),
            **_col("track_changes", dt.track_changes),
            **_col("autoname", dt.autoname),
            **_col("title_field", dt.title_field),
            **_col("image_field", dt.image_field),
            **_col("default_view", dt.default_view),
            **_col("table_name", dt.table_name),
            **_col("search_fields", dt.search_fields if dt.search_fields else None),
            **_col("is_tree", dt.is_tree),
            **_col("tree_view", dt.tree_view.model_dump() if dt.tree_view else None),
            **_col("show_in_dashboard", dt.show_in_dashboard),
            **_col("dashboard_doctype", dt.dashboard_doctype),
            **_col("fetch_from", dt.fetch_from),
        }

        if dt.name in existing_names:
            await conn.execute(
                table.update()
                .where(table.c.name == dt.name)
                .values(modified_at=now, **scalar_fields)
            )
        else:
            await conn.execute(
                table.insert().values(
                    id=str(uuid.uuid4()),
                    name=dt.name,
                    owner="system",
                    created_at=now,
                    modified_at=now,
                    modified_by="system",
                    docstatus=0,
                    **scalar_fields,
                )
            )

    registered_names = {dt.name for dt in all_doctypes}
    stale = existing_names - registered_names
    for name in stale:
        await conn.execute(table.delete().where(table.c.name == name))

    if stale:
        logger.info("startup.doctype_table_cleaned", removed=sorted(stale))
    logger.info("startup.doctype_table_synced", count=len(all_doctypes))


async def sync_all_doctypes(session: AsyncSession, engine: AsyncEngine) -> None:
    """Synchronize physical tables for ALL DocTypes in the registry.

    Iterates through all DocTypes and calls ``sync_table()`` for each.
    This ensures that new fields in JSON files are added to the DB.
    """
    from grunt.core.metadata.compiler import sync_table  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    # Ensure all doctypes (even user-created ones) are in the registry memory
    await doctype_registry.load_all(session)
    doctypes = await doctype_registry.list_all()

    for dt in doctypes:
        try:
            await sync_table(dt, engine, session=session)
        except Exception as e:  # noqa: BLE001
            logger.warning("startup.sync_doctype_failed", name=dt.name, error=str(e))
