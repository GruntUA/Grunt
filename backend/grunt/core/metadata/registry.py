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
from grunt.core.metadata.system_doctypes import SYSTEM_DOCTYPES, is_system_doctype
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
        """Load all DocTypes from ``grunt_meta_doctype`` into memory.

        System DocTypes (like "DocType" itself) are injected automatically
        and cannot be overridden by user-defined ones.
        """
        result = await session.execute(select(GruntMetaDoctype))
        rows = result.scalars().all()
        self._doctypes.clear()

        # Inject core system DocTypes first
        for name, dt in SYSTEM_DOCTYPES.items():
            self._doctypes[name] = dt

        for row in rows:
            if row.name in SYSTEM_DOCTYPES:
                continue  # system DocTypes are authoritative
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DocType '{name}' not found",
            )
        return dt

    async def list_all(self) -> list[DocType]:
        """Return all registered DocTypes."""
        return list(self._doctypes.values())

    # ── Write ────────────────────────────────────────────────────────────

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
        if is_system_doctype(doctype.name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"System DocType '{doctype.name}' cannot be modified",
            )
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
        if is_system_doctype(name):
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
        if is_system_doctype(doctype.name):
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
