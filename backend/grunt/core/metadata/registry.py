"""DocType Registry — in-memory cache of DocType definitions with lazy loading.

Source of truth: ``grunt_meta_doctype`` table (JSON column ``data``).

Startup behaviour
-----------------
* Core/system DocTypes are loaded eagerly (they need table sync on first run).
* User-created DocTypes are **lazy-loaded**: only their names are fetched at
  startup; the full definition is loaded from the DB the first time
  ``get(name)`` is called for that DocType.

This keeps startup fast regardless of how many DocTypes an application has.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException, status
from sqlalchemy import delete, select, update

from grunt.core.db.system_tables import GruntMetaDoctype
from grunt.core.metadata.compiler import sync_table
from grunt.core.metadata.doctype import DocType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()


class DocTypeRegistry:
    """Singleton registry with lazy loading for user-created DocTypes."""

    def __init__(self) -> None:
        self._doctypes: dict[str, DocType] = {}
        # Names that exist in the DB but whose definitions are not yet loaded.
        self._known_names: set[str] = set()

    # ── Read ─────────────────────────────────────────────────────────────

    async def prefetch_names(self, session: AsyncSession) -> None:
        """Record names of all user-created DocTypes without loading their data.

        Call this at startup instead of :meth:`load_all`. Core/system DocTypes
        are already in ``_doctypes``; their names are excluded from
        ``_known_names`` so they are never lazy-loaded (their definition is
        already in memory).
        """
        result = await session.execute(select(GruntMetaDoctype.name))
        all_names = {row[0] for row in result}
        self._known_names = all_names - set(self._doctypes)
        logger.info(
            "registry.names_prefetched",
            core=len(self._doctypes),
            lazy=len(self._known_names),
        )

    async def load_all(self, session: AsyncSession) -> None:
        """Eagerly load ALL user-created DocTypes into memory.

        Used by CLI commands and migration tooling that need the full registry
        available synchronously. For the web server, prefer
        :meth:`prefetch_names` + lazy loading via :meth:`get`.
        """
        result = await session.execute(select(GruntMetaDoctype))
        rows = result.scalars().all()

        for row in rows:
            if row.name in self._doctypes:
                continue  # already loaded (core doctype)
            try:
                dt = DocType.model_validate(row.data)
                self._doctypes[dt.name] = dt
                self._known_names.discard(dt.name)
            except Exception:
                logger.warning("registry.skip_invalid", name=row.name)
        logger.info("registry.loaded", count=len(self._doctypes))

    async def _lazy_load(self, name: str) -> DocType | None:
        """Load a single DocType from the DB and cache it."""
        from grunt.core.site.manager import site_manager  # noqa: PLC0415

        try:
            site_name = site_manager.get_active_site()
            maker = site_manager.get_session_maker(site_name)
        except Exception:
            return None

        async with maker() as session:
            result = await session.execute(
                select(GruntMetaDoctype).where(GruntMetaDoctype.name == name)
            )
            row = result.scalar_one_or_none()

        if row is None:
            return None

        try:
            dt = DocType.model_validate(row.data)
        except Exception:
            logger.warning("registry.lazy_load_invalid", name=name)
            return None

        self._doctypes[dt.name] = dt
        self._known_names.discard(dt.name)
        logger.debug("registry.lazy_loaded", name=dt.name)
        return dt

    async def get(self, name: str) -> DocType:
        """Return a DocType by name, lazy-loading from DB if necessary."""
        # 1. Fast path — already in memory
        dt = self._doctypes.get(name)
        if dt is not None:
            return dt

        # 2. Case-insensitive + plural/singular fallbacks (in-memory only)
        name_lower = name.lower()
        for k, v in self._doctypes.items():
            if k.lower() == name_lower:
                return v

        if name_lower.endswith("s"):
            singular = name[:-1]
            for k, v in self._doctypes.items():
                if k.lower() == singular.lower():
                    return v
        else:
            plural = name + "s"
            for k, v in self._doctypes.items():
                if k.lower() == plural.lower():
                    return v

        # 3. Lazy-load from DB (if name is known to exist)
        candidate = name
        if candidate not in self._known_names:
            # Try same fuzzy matches against _known_names
            for k in self._known_names:
                if k.lower() == name_lower:
                    candidate = k
                    break
            else:
                candidate = ""

        if candidate:
            dt = await self._lazy_load(candidate)
            if dt is not None:
                return dt

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DocType '{name}' not found",
        )

    async def list_all(self) -> list[DocType]:
        """Return all registered DocTypes, loading any that are still lazy."""
        if self._known_names:
            # Load remaining lazy DocTypes so the list is complete
            from grunt.core.site.manager import site_manager  # noqa: PLC0415

            try:
                site_name = site_manager.get_active_site()
                maker = site_manager.get_session_maker(site_name)
                async with maker() as session:
                    await self.load_all(session)
            except Exception as exc:
                logger.warning("registry.list_all_lazy_failed", error=str(exc))

        return list(self._doctypes.values())

    def is_system(self, name: str) -> bool:
        """Return True if the named DocType is a built-in system DocType."""
        dt = self._doctypes.get(name)
        return dt is not None and dt.is_system

    # ── Write ────────────────────────────────────────────────────────────

    async def _inject_core(
        self,
        doctype: DocType,
        session: AsyncSession,
        async_engine: AsyncEngine | None = None,
    ) -> None:
        """Register a core (is_system=True) DocType from JSON.

        Loads the definition into the registry and keeps ``grunt_meta_doctype``
        up to date (seeding on first run, merging new fields on upgrades).

        Physical table creation/migration is intentionally NOT done here —
        run ``grunt migrate`` to synchronise DB schema with DocType definitions.
        """
        existing_row = await session.execute(
            select(GruntMetaDoctype).where(GruntMetaDoctype.name == doctype.name)
        )
        existing = existing_row.scalar_one_or_none()

        if existing:
            # Virtual DocTypes have no physical DB tables, so there is nothing
            # to migrate and no risk of data loss.  Always keep them in sync
            # with the bundled JSON so that field changes take effect on restart.
            if doctype.is_virtual:
                active_dt = doctype
                await session.execute(
                    update(GruntMetaDoctype)
                    .where(GruntMetaDoctype.name == doctype.name)
                    .values(module=doctype.module, data=doctype.model_dump())
                )
            else:
                # Load the stored definition (preserves Studio customisations).
                try:
                    active_dt = DocType.model_validate(existing.data)
                except Exception:
                    # Stored data is invalid — fall back to JSON and repair.
                    logger.warning(
                        "registry.core_stored_invalid",
                        name=doctype.name,
                        action="falling_back_to_json",
                    )
                    active_dt = doctype
                    await session.execute(
                        update(GruntMetaDoctype)
                        .where(GruntMetaDoctype.name == doctype.name)
                        .values(module=doctype.module, data=doctype.model_dump())
                    )
                else:
                    # Merge: add fields from JSON that are missing in the stored
                    # definition (framework upgrades).  Never remove existing fields.
                    stored_fieldnames = {f.fieldname: f for f in active_dt.fields}
                    new_fields = [f for f in doctype.fields if f.fieldname not in stored_fieldnames]
                    if new_fields:
                        active_dt.fields.extend(new_fields)
                        logger.info(
                            "registry.core_fields_merged",
                            name=doctype.name,
                            added=[f.fieldname for f in new_fields],
                        )
                    # Sync default values for existing fields from JSON
                    for json_field in doctype.fields:
                        stored_field = stored_fieldnames.get(json_field.fieldname)
                        if stored_field is not None and stored_field.default != json_field.default:
                            stored_field.default = json_field.default
                    # Persist the merged definition and keep module in sync.
                    # Wrapped separately so a transient DB lock does not prevent
                    # the physical table sync or in-memory registration below.
                    try:
                        await session.execute(
                            update(GruntMetaDoctype)
                            .where(GruntMetaDoctype.name == doctype.name)
                            .values(module=doctype.module, data=active_dt.model_dump())
                        )
                        await session.flush()
                    except Exception as _upd_err:  # noqa: BLE001
                        logger.warning(
                            "registry.core_metadata_update_failed",
                            name=doctype.name,
                            error=str(_upd_err),
                        )
        else:
            # First run: seed from the bundled JSON file.
            session.add(
                GruntMetaDoctype(
                    name=doctype.name,
                    module=doctype.module,
                    data=doctype.model_dump(),
                )
            )
            active_dt = doctype
            await session.flush()

        self._doctypes[active_dt.name] = active_dt
        logger.info("registry.core_injected", name=active_dt.name)

    async def register(
        self,
        doctype: DocType,
        session: AsyncSession,
        async_engine: AsyncEngine,
    ) -> None:
        """Validate, persist, sync table, and cache a new DocType."""
        self._validate_new(doctype)

        # Persist to DB
        row = GruntMetaDoctype(
            name=doctype.name,
            module=doctype.module,
            data=doctype.model_dump(),
        )
        session.add(row)
        await session.flush()

        # Create / update physical table (pass session to avoid SQLite locking)
        await sync_table(doctype, async_engine, session=session)

        # Cache
        self._doctypes[doctype.name] = doctype
        self._known_names.discard(doctype.name)
        logger.info("registry.registered", name=doctype.name)

    async def update(
        self,
        doctype: DocType,
        session: AsyncSession,
        async_engine: AsyncEngine,
    ) -> None:
        """Update an existing DocType, re-sync its table, refresh cache."""
        if doctype.name not in self._doctypes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DocType '{doctype.name}' not found",
            )
        self._validate_fields(doctype)

        await session.execute(
            update(GruntMetaDoctype)
            .where(GruntMetaDoctype.name == doctype.name)
            .values(module=doctype.module, data=doctype.model_dump())
        )
        await session.flush()

        await sync_table(doctype, async_engine, session=session)
        self._doctypes[doctype.name] = doctype
        logger.info("registry.updated", name=doctype.name)

    async def delete(self, name: str, session: AsyncSession) -> None:
        """Remove DocType from registry and DB. Physical table is NOT dropped."""
        if self.is_system(name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"System DocType '{name}' cannot be deleted",
            )
        if name not in self._doctypes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DocType '{name}' not found",
            )
        await session.execute(delete(GruntMetaDoctype).where(GruntMetaDoctype.name == name))
        await session.flush()
        self._doctypes.pop(name, None)
        self._known_names.discard(name)
        logger.info("registry.deleted", name=name)

    # ── Validation helpers ───────────────────────────────────────────────

    def _validate_new(self, doctype: DocType) -> None:
        """Ensure name is unique, not a system DocType, and fields are valid."""
        if doctype.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype.name}' is a reserved system DocType name",
            )
        if doctype.name in self._doctypes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"DocType '{doctype.name}' already exists",
            )
        self._validate_fields(doctype)

    @staticmethod
    def _validate_fields(doctype: DocType) -> None:
        """Check for duplicate fieldnames."""
        seen: set[str] = set()
        for f in doctype.fields:
            if f.fieldname in seen:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Duplicate fieldname '{f.fieldname}' in DocType '{doctype.name}'",
                )
            seen.add(f.fieldname)


# Module-level singleton
doctype_registry = DocTypeRegistry()
