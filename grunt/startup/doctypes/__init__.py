"""Startup - DocType registry bootstrap and population."""

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt import log
from grunt.db.schema.apply import DuplicateDataError
from grunt.metadata import store
from grunt.metadata.compiler import sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.extensions import DoctypeExtension, apply_extensions
from grunt.metadata.registry import doctype_registry

_GRUNT_ROOT = Path(__file__).parent.parent.parent  # grunt/startup/doctypes/ -> grunt/


def _find_doctype_dirs(_root=None):
    """Return all grunt/*/doctypes/ directories."""
    root = _root or _GRUNT_ROOT
    return [p for p in root.glob("*/doctypes") if p.is_dir()]


def _core_doctype_files() -> list[Path]:
    return sorted(f for d in _find_doctype_dirs() for f in d.glob("**/*.json"))


def _read_core_doctype(
    dt_file: Path, extensions: dict[str, list[DoctypeExtension]] | None
) -> DocType | None:
    dt_data = json.loads(dt_file.read_text())
    dt_name = dt_data.get("name", "")
    if not dt_name:
        return None
    dt_obj = DocType.model_validate(dt_data)
    if not dt_obj.app:
        dt_obj.app = "grunt"
    return apply_extensions(dt_obj, (extensions or {}).get(dt_name))


def bundled_core_doctypes(
    extensions: dict[str, list[DoctypeExtension]] | None = None,
) -> list[DocType]:
    """The core DocTypes as their JSON defines them (with *extensions*) - no
    database: what a fresh site gets (``grunt migrate --dry-run`` plans it)."""
    found = (_read_core_doctype(f, extensions) for f in _core_doctype_files())
    return [dt for dt in found if dt is not None]


async def load_core_doctypes(
    session: AsyncSession,
    sync_db: bool = False,
    extensions: dict[str, list[DoctypeExtension]] | None = None,
) -> None:
    """Register DocTypes defined as JSON files in grunt/*/doctypes/.

    Scans all module-level doctypes/ directories within the grunt package.
    Uses _inject_core to bypass user-facing validation. *extensions* - the
    fields installed apps add to core DocTypes (``extensions_for_site``),
    merged into the JSON before it is compared with the stored definition.
    """
    if sync_db:
        await store.ensure_table(session)

    for dt_file in _core_doctype_files():
        try:
            dt_obj = _read_core_doctype(dt_file, extensions)
            if dt_obj is None:
                continue
            await doctype_registry._inject_core(dt_obj, session, sync_db=sync_db)
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
