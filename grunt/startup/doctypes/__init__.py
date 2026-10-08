"""Startup - DocType registry bootstrap and population."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from grunt import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import json

from grunt.hooks import DOCTYPE_OVERRIDES
from grunt.metadata import store
from grunt.metadata.compiler import DuplicateDataError, sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.field import DocField
from grunt.metadata.registry import doctype_registry

_GRUNT_ROOT = Path(__file__).parent.parent.parent  # grunt/startup/doctypes/ -> grunt/


def _find_doctype_dirs(_root=None):
    """Return all grunt/*/doctypes/ directories."""
    root = _root or _GRUNT_ROOT
    return [p for p in root.glob("*/doctypes") if p.is_dir()]


async def apply_doctype_overrides(
    session: AsyncSession, engine: AsyncEngine, sync_db: bool = False
) -> None:
    """Apply field extensions registered by apps via ``doctype_overrides`` in hooks.py.

    For each DocType listed in ``hooks.DOCTYPE_OVERRIDES``, new fields that are
    not yet present are appended to the DocType definition.

    Physical table changes (ALTER TABLE) are NOT applied here - run
    ``grunt migrate`` to synchronise DB schema with DocType definitions.

    Only called from ``grunt migrate`` (with ``sync_db=True``, so the
    merged result is persisted into the DocType table - the server never
    re-runs this merge at boot, so without persistence the added fields would
    be lost the moment the DocType is next lazy-loaded from a fresh process).
    """
    if not DOCTYPE_OVERRIDES:
        return

    for doctype_name, spec in DOCTYPE_OVERRIDES.items():
        dt = await doctype_registry.get_or_none(doctype_name)
        if dt is None:
            log.warning("startup.override_doctype_not_found", doctype=doctype_name)
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
            except Exception as e:
                log.warning(
                    "startup.override_field_invalid",
                    doctype=doctype_name,
                    field=fname,
                    error=str(e),
                )

        if added:
            log.info(
                "startup.doctype_overrides_applied",
                doctype=doctype_name,
                added_fields=added,
            )
            if sync_db:
                await store.update_doctype(session, dt)
                await session.flush()


async def load_core_doctypes(session: AsyncSession, sync_db: bool = False) -> None:
    """Register DocTypes defined as JSON files in grunt/*/doctypes/.

    Scans all module-level doctypes/ directories within the grunt package.
    Uses _inject_core to bypass user-facing validation.
    """
    if sync_db:
        await store.ensure_table(session)

    dt_files = sorted(f for d in _find_doctype_dirs() for f in d.glob("**/*.json"))

    for dt_file in dt_files:
        try:
            dt_data = json.loads(dt_file.read_text(encoding="utf-8"))
            dt_name = dt_data.get("name", "")
            if not dt_name:
                continue
            dt_obj = DocType.model_validate(dt_data)
            if not dt_obj.app:
                dt_obj.app = "grunt"
            await doctype_registry._inject_core(dt_obj, session, sync_db=sync_db)
            if sync_db:
                log.info("startup.core_doctype_injected", doctype=dt_name)
        except Exception as e:
            # Boot tolerates a broken file; a sync (migrate) must not report
            # success with the DocType table left stale.
            if sync_db:
                raise RuntimeError(f"core DocType {dt_file.name}: {e}") from e
            log.warning("startup.core_doctype_failed", file=dt_file.name, error=str(e))


async def sync_all_doctypes(session: AsyncSession, engine: AsyncEngine) -> None:
    """Synchronize physical tables for ALL DocTypes in the registry.

    Iterates through all DocTypes and calls ``sync_table()`` for each.
    This ensures that new fields in JSON files are added to the DB.
    """
    # Ensure all doctypes (even user-created ones) are in the registry memory
    await doctype_registry.load_all(session)
    doctypes = await doctype_registry.list_all()

    for dt in doctypes:
        try:
            await sync_table(dt, engine, session=session)
        except DuplicateDataError as e:
            log.warning("startup.sync_doctype_duplicates", name=dt.name, detail=str(e))
        except Exception as e:
            log.warning("startup.sync_doctype_failed", name=dt.name, error=str(e))
