"""DocType Registry — singleton in-memory cache of all DocType definitions.

Source of truth: ``grunt_meta_doctype`` table (JSON column ``data``).
On application startup the registry loads all rows into memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException, status
from sqlalchemy import delete, select, update

from grunt.core.metadata.compiler import sync_table
from grunt.core.metadata.doctype import DocType
from grunt.core.db.system_tables import GruntMetaDoctype

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()


class DocTypeRegistry:
    """Singleton registry — keeps every registered DocType in ``_doctypes``."""

    def __init__(self) -> None:
        self._doctypes: dict[str, DocType] = {}

    # ── Read ─────────────────────────────────────────────────────────────

    async def load_all(self, session: AsyncSession) -> None:
        """Load user-created DocTypes from ``grunt_meta_doctype`` into memory.

        Core/system DocTypes (is_system=True) are loaded separately via
        load_core_doctypes() and are already in _doctypes — skip them here.
        """
        result = await session.execute(select(GruntMetaDoctype))
        rows = result.scalars().all()

        for row in rows:
            if row.name in self._doctypes:
                continue  # already loaded (core doctype)
            try:
                dt = DocType.model_validate(row.data)
                self._doctypes[dt.name] = dt
            except Exception:
                logger.warning("registry.skip_invalid", name=row.name)
        logger.info("registry.loaded", count=len(self._doctypes))

    async def get(self, name: str) -> DocType:
        """Return a DocType by name or raise HTTP 404."""
        dt = self._doctypes.get(name)
        if dt is None:
            # Fallback to case-insensitive match
            for k, v in self._doctypes.items():
                if k.lower() == name.lower():
                    return v
            
            # Simple plural/singular fallback for common UI requests (e.g. 'users' -> 'User')
            if name.lower().endswith('s'):
                singular = name[:-1]
                for k, v in self._doctypes.items():
                    if k.lower() == singular.lower():
                        return v
            elif not name.lower().endswith('s'):
                plural = name + 's'
                for k, v in self._doctypes.items():
                    if k.lower() == plural.lower():
                        return v

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DocType '{name}' not found",
            )
        return dt

    async def list_all(self) -> list[DocType]:
        """Return all registered DocTypes."""
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
        async_engine: AsyncEngine,
    ) -> None:
        """Register a core (is_system=True) DocType from JSON.

        On first run (no DB row): inserts from JSON and syncs physical table.
        On subsequent runs (DB row exists): preserves the stored ``data`` so
        that superadmin edits made via Studio Builder are not overwritten.
        Only updates the ``module`` metadata field. Physical table is synced
        from the stored definition (to pick up any columns added by Studio).
        """
        existing_row = await session.execute(
            select(GruntMetaDoctype).where(GruntMetaDoctype.name == doctype.name)
        )
        existing = existing_row.scalar_one_or_none()

        if existing:
            # Preserve user customisations — do NOT overwrite data from JSON.
            # Only keep module in sync (rarely changes).
            await session.execute(
                update(GruntMetaDoctype)
                .where(GruntMetaDoctype.name == doctype.name)
                .values(module=doctype.module)
            )
            # Load the stored definition for table sync & in-memory cache.
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
                    .values(data=doctype.model_dump())
                )
        else:
            # First run: seed from the bundled JSON file.
            session.add(GruntMetaDoctype(
                name=doctype.name,
                module=doctype.module,
                data=doctype.model_dump(),
            ))
            active_dt = doctype

        await session.flush()
        await sync_table(active_dt, async_engine, session=session)
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
        await session.execute(
            delete(GruntMetaDoctype).where(GruntMetaDoctype.name == name)
        )
        await session.flush()
        del self._doctypes[name]
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
