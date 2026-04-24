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
from grunt.core.metadata.compiler import invalidate_table_cache, sync_table
from grunt.core.metadata.doctype import DocType
from grunt.core.permissions.rbac import invalidate_permission_cache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()


class DocTypeRegistry:
    """Singleton registry with lazy loading for user-created DocTypes."""

    def __init__(self) -> None:
        self._doctypes: dict[str, DocType] = {}
        # Names that exist in the DB but whose definitions are not yet loaded.
        self._known_names: set[str] = set()

        # O(1) case-insensitive lookup indices.
        # Maps name.lower() → canonical name.  Updated by every write method.
        self._lower_index: dict[str, str] = {}  # for loaded _doctypes
        self._known_lower: dict[str, str] = {}  # for lazy _known_names

    # ── Index helpers ─────────────────────────────────────────────────────

    def _index_add(self, name: str) -> None:
        """Add *name* to the loaded-doctype index."""
        self._lower_index[name.lower()] = name

    def _index_remove(self, name: str) -> None:
        """Remove *name* from the loaded-doctype index (if present)."""
        self._lower_index.pop(name.lower(), None)

    def _known_index_add(self, name: str) -> None:
        self._known_lower[name.lower()] = name

    def _known_index_remove(self, name: str) -> None:
        self._known_lower.pop(name.lower(), None)

    def clear_cache(self) -> None:
        """Clear all in-memory DocType definitions and known names.

        This forces the registry to re-fetch metadata from the database
        (or core JSON files) on the next access.
        """
        self._doctypes.clear()
        self._known_names.clear()
        self._lower_index.clear()
        self._known_lower.clear()
        logger.info("registry.cache_cleared")

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
        # Rebuild the known-names index in one pass
        self._known_lower = {n.lower(): n for n in self._known_names}
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
                self._index_add(dt.name)
                self._known_names.discard(dt.name)
                self._known_index_remove(dt.name)
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
        self._index_add(dt.name)
        self._known_names.discard(dt.name)
        self._known_index_remove(dt.name)
        logger.debug("registry.lazy_loaded", name=dt.name)
        return dt

    async def get(self, name: str) -> DocType:
        """Return a DocType by name, lazy-loading from DB if necessary.

        Lookup order (all O(1)):
        1. Exact match in loaded doctypes.
        2. Case-insensitive match in loaded doctypes via ``_lower_index``.
        3. Singular/plural heuristic via ``_lower_index`` (e.g. "customer" → "Customer").
        4. Case-insensitive match in lazy ``_known_names`` via ``_known_lower``,
           then load from DB.
        """
        # 1. Exact match — O(1)
        dt = self._doctypes.get(name)
        if dt is not None:
            return dt

        name_lower = name.lower()

        # 2. Case-insensitive match against loaded doctypes — O(1)
        canonical = self._lower_index.get(name_lower)
        if canonical:
            return self._doctypes[canonical]

        # 3. Singular/plural heuristic against loaded doctypes — O(1)
        if name_lower.endswith("s"):
            canonical = self._lower_index.get(name_lower[:-1])
        else:
            canonical = self._lower_index.get(name_lower + "s")
        if canonical:
            return self._doctypes[canonical]

        # 4. Resolve against lazy known-names index — O(1)
        candidate = (
            name
            if name in self._known_names
            else self._known_lower.get(name_lower)
            or (self._known_lower.get(name_lower[:-1]) if name_lower.endswith("s") else None)
            or (self._known_lower.get(name_lower + "s"))
        )

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

    # ── Write ────────────────────────────────────────────────────────────

    async def _inject_core(
        self,
        doctype: DocType,
        session: AsyncSession,
        sync_db: bool = False,
    ) -> None:
        """Register a core DocType from JSON.

        Loads the definition into the registry. If sync_db is True, keeps
        ``grunt_meta_doctype`` up to date (seeding on first run, merging new fields
        on upgrades). If False, only merges new fields in memory.
        """
        existing_row = await session.execute(
            select(GruntMetaDoctype).where(GruntMetaDoctype.name == doctype.name)
        )
        existing = existing_row.scalar_one_or_none()

        if existing:
            # Virtual DocTypes have no physical DB tables, so there is nothing
            # to migrate and no risk of data loss. Always use memory version.
            if doctype.is_virtual:
                active_dt = doctype
                if sync_db:
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
                    if sync_db:
                        await session.execute(
                            update(GruntMetaDoctype)
                            .where(GruntMetaDoctype.name == doctype.name)
                            .values(module=doctype.module, data=doctype.model_dump())
                        )
                else:
                    # Merge logic
                    stored_fieldnames = {f.fieldname: f for f in active_dt.fields}
                    new_fields = [f for f in doctype.fields if f.fieldname not in stored_fieldnames]
                    if new_fields:
                        active_dt.fields.extend(new_fields)
                        if sync_db:
                            logger.info(
                                "registry.core_fields_merged",
                                name=doctype.name,
                                added=[f.fieldname for f in new_fields],
                            )
                    # Sync top-level structural properties from JSON
                    _TOP_STRUCTURAL = {"is_tree", "is_submittable", "title_field", "tree_view", "search_fields", "label", "module"}
                    for attr in _TOP_STRUCTURAL:
                        json_val = getattr(doctype, attr, None)
                        if json_val is not None and getattr(active_dt, attr, None) != json_val:
                            setattr(active_dt, attr, json_val)

                    # Sync field-level structural properties from JSON (fieldtype, options, label, default, etc.)
                    _STRUCTURAL = {
                        "fieldtype", "options", "label", "default", "read_only",
                        "required", "hidden", "in_list_view", "in_filter", "description",
                    }
                    for json_field in doctype.fields:
                        stored_field = stored_fieldnames.get(json_field.fieldname)
                        if stored_field is None:
                            continue
                        for attr in _STRUCTURAL:
                            if getattr(stored_field, attr, None) != getattr(json_field, attr, None):
                                setattr(stored_field, attr, getattr(json_field, attr, None))

                    # Sync field order: position JSON-defined fields according to JSON order, 
                    # followed by any custom fields that were added locally.
                    json_order = {f.fieldname: i for i, f in enumerate(doctype.fields)}
                    active_dt.fields.sort(
                        key=lambda f: json_order.get(f.fieldname, 9999)
                    )

                    if sync_db:
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
            active_dt = doctype
            if sync_db:
                session.add(
                    GruntMetaDoctype(
                        name=doctype.name,
                        module=doctype.module,
                        data=doctype.model_dump(),
                    )
                )
                await session.flush()

        self._doctypes[active_dt.name] = active_dt
        self._index_add(active_dt.name)
        if sync_db:
            logger.info("registry.core_injected", name=active_dt.name)
        else:
            logger.info("registry.core_loaded", name=active_dt.name)

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
        self._index_add(doctype.name)
        self._known_names.discard(doctype.name)
        self._known_index_remove(doctype.name)
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

        # Invalidate caches BEFORE sync so compile_doctype_to_table() rebuilds
        # the Table with the new column list when sync_table calls it internally.
        invalidate_table_cache(doctype.name)
        invalidate_permission_cache(doctype.name)
        await sync_table(doctype, async_engine, session=session)
        self._doctypes[doctype.name] = doctype
        self._index_add(doctype.name)
        logger.info("registry.updated", name=doctype.name)

    async def delete(self, name: str, session: AsyncSession) -> None:
        """Remove DocType from registry and DB. Physical table is NOT dropped."""
        if name not in self._doctypes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DocType '{name}' not found",
            )
        await session.execute(delete(GruntMetaDoctype).where(GruntMetaDoctype.name == name))
        await session.flush()
        self._doctypes.pop(name, None)
        self._index_remove(name)
        self._known_names.discard(name)
        self._known_index_remove(name)
        invalidate_table_cache(name)
        invalidate_permission_cache(name)
        logger.info("registry.deleted", name=name)

    # ── Validation helpers ───────────────────────────────────────────────

    def _validate_new(self, doctype: DocType) -> None:
        """Ensure name is unique and fields are valid."""
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
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Duplicate fieldname '{f.fieldname}' in DocType '{doctype.name}'",
                )
            seen.add(f.fieldname)


# Module-level singleton
doctype_registry = DocTypeRegistry()
