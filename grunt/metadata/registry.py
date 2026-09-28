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

import re
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from grunt import _, log
from grunt.db.system_tables import GruntMetaDoctype
from grunt.metadata.compiler import invalidate_table_cache, sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.field import DocField
from grunt.permissions.rbac import invalidate_permission_cache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.document.meta import Meta


_FIELDNAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_MAX_FIELDNAME_LEN = 64

# Top-level DocType properties that _inject_core() always overwrites from the
# bundled core JSON on every load. Anything NOT listed here (permissions,
# autoname, ...) is treated as a Studio/user
# customization: the JSON only seeds it on first run and never touches it again.
# Adding a new core-authoritative property to DocType? Add it here too.
_CORE_SYNCED_DOCTYPE_ATTRS = frozenset(
    {
        "is_child",
        "is_singleton",
        "is_virtual",
        "is_tree",
        "is_log",
        "is_submittable",
        "track_seen",
        "track_views",
        "track_activity",
        "hide_from_activity_feed",
        "public_attachments",
        "inherit_permission_from",
        "quick_entry",
        "has_web_view",
        "allow_guest_to_view",
        "index_web_pages_for_search",
        "web_route",
        "is_published_field",
        "beta",
        "deprecated",
        "title_field",
        "description",
        "tree_parent_field",
        "tree_title_field",
        "tree_as_of_date_field",
        "tree_sort_by",
        "tree_sort_order",
        "search_fields",
        "label",
        "module",
        "app",
    }
)

# Per-field properties that _inject_core() always overwrites from the bundled
# core JSON — same rationale as _CORE_SYNCED_DOCTYPE_ATTRS, at field level.
_CORE_SYNCED_FIELD_ATTRS = frozenset(
    {
        "fieldtype",
        "options",
        "options_source",
        "label",
        "default",
        "read_only",
        "required",
        "hidden",
        "in_list_view",
        "in_filter",
        "description",
        "depends_on",
        "bold",
        "in_quick_entry",
        "in_quick_filter",
        "is_virtual",
        "read_formula",
        "validator",
        "tab_component",
    }
)


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
        """Clear in-memory DocType definitions so they are re-fetched from the DB.

        All currently loaded DocType names (including core DocTypes) are moved
        to ``_known_names`` before clearing ``_doctypes``, so the lazy-load path
        in :meth:`get` can still find them on the next access without a server
        restart.
        """
        # Promote every loaded DocType name to the lazy-known set so _lazy_load
        # can re-fetch its definition from the DB on the next request.
        for name in self._doctypes:
            self._known_names.add(name)
            self._known_lower[name.lower()] = name

        self._doctypes.clear()
        self._lower_index.clear()
        log.info("registry.cache_cleared")

    def reset(self) -> None:
        """Discard ALL in-memory state — loaded DocTypes and the known-names
        index alike.

        Test-harness use only: unlike :meth:`clear_cache` (which demotes
        loaded DocTypes to "known, reload from DB on next :meth:`get`"),
        fixtures that repopulate the registry directly (bypassing the DB —
        parsing JSON files straight into ``_doctypes``) need every index
        wiped, not demoted, or a name reused across tests can resolve
        through a stale ``_lower_index``/``_known_lower`` entry left over
        from a previous test's state.
        """
        self._doctypes.clear()
        self._known_names.clear()
        self._lower_index.clear()
        self._known_lower.clear()

    # ── Read ─────────────────────────────────────────────────────────────

    async def prefetch_names(self, session: AsyncSession) -> None:
        """Record names of ALL DocTypes (core and user-created alike) without
        loading their data.

        Call this at startup instead of :meth:`load_all`. Full definitions —
        core or user — are loaded lazily from ``grunt_meta_doctype`` on first
        :meth:`get`. Schema/definition merging from bundled core JSON only
        happens via ``grunt db migrate``, which persists the merged result
        into ``grunt_meta_doctype`` so the server never needs to touch the
        JSON files at runtime.

        Swallows a missing/not-yet-migrated ``grunt_meta_doctype`` table so a
        brand-new site can still boot before its first ``grunt db migrate``.
        """
        try:
            result = await session.execute(select(GruntMetaDoctype.c.name))
            all_names = {row[0] for row in result}
        except Exception:
            log.info("registry.prefetch_names_table_missing", hint="run `grunt db migrate` first")
            all_names = set()
        self._known_names = all_names - set(self._doctypes)
        # Rebuild the known-names index in one pass
        self._known_lower = {n.lower(): n for n in self._known_names}
        log.info(
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
        rows = result.mappings().all()

        for row in rows:
            if row["name"] in self._doctypes:
                continue  # already loaded (core doctype)
            try:
                dt = DocType.model_validate(row["data"])
                # Mirrors _lazy_load: a stale cached Table (compiler.py's
                # _TABLE_CACHE) would keep excluding columns for fields added
                # since it was built — e.g. after the hot-reload middleware's
                # clear_cache() + list_all() picks up a schema change made by
                # `grunt migrate` in another process, reads would silently
                # keep missing the new column until a full restart.
                invalidate_table_cache(dt.name)
                self._doctypes[dt.name] = dt
                self._index_add(dt.name)
                self._known_names.discard(dt.name)
                self._known_index_remove(dt.name)
            except Exception:
                log.warning("registry.skip_invalid", name=row.name)
        log.info("registry.loaded", count=len(self._doctypes))

    async def _lazy_load(self, name: str) -> DocType | None:
        """Load a single DocType from the DB and cache it.

        Prefers the ambient request/test session (whatever ``grunt.context()``
        currently has bound) over site_manager's own per-site session.
        site_manager resolves "the current site" via a process-global fallback
        (``sites/currentsite.txt`` when no ContextVar is set) — correct for a
        real, single-site request, but wrong the moment more than one site's
        database is reachable from the same process (e.g. a dev box that also
        runs the test suite): an ambient session already means "this call is
        happening against a specific, known database", so reuse it instead of
        letting site_manager guess. Only falls back to site_manager when
        nothing is bound — background tasks/schedulers with their own raw
        session still work exactly as before.
        """
        from grunt.local import _session_ctx

        active_session = _session_ctx.get()
        if active_session is not None:
            result = await active_session.execute(
                select(GruntMetaDoctype).where(GruntMetaDoctype.c.name == name)
            )
            row = result.mappings().one_or_none()
        else:
            from grunt.site.manager import site_manager

            # Fail closed on ANY failure in this path — not just resolving
            # site_name/maker, but opening the connection and running the
            # query too (engine creation is lazy, so a nonexistent/misconfigured
            # site only fails once actually connected). A background task
            # with no ambient session must return None, never crash, on a
            # bad site resolution.
            try:
                site_name = site_manager.get_active_site()
                maker = site_manager.get_session_maker(site_name)
                async with maker() as session:
                    result = await session.execute(
                        select(GruntMetaDoctype).where(GruntMetaDoctype.c.name == name)
                    )
                    row = result.mappings().one_or_none()
            except Exception:
                return None

        if row is None:
            return None

        try:
            dt = DocType.model_validate(row["data"])
        except Exception:
            log.warning("registry.lazy_load_invalid", name=name)
            return None

        invalidate_table_cache(dt.name)
        self._doctypes[dt.name] = dt
        self._index_add(dt.name)
        self._known_names.discard(dt.name)
        self._known_index_remove(dt.name)
        log.debug("registry.lazy_loaded", name=dt.name)
        return dt

    async def get(self, name: str) -> DocType:
        """Return a DocType by name, lazy-loading from DB if necessary.

        Lookup order (all O(1)):
        1. Exact match in loaded doctypes.
        2. Case-insensitive match in loaded doctypes via ``_lower_index``.
        3. Case-insensitive match in lazy ``_known_names`` via ``_known_lower``,
           then load from DB.

        Deliberately no singular/plural guessing — a DocType is matched by its
        real name only, never by a heuristically inferred one.
        """
        # 1. Exact match — O(1)
        dt = self._doctypes.get(name)
        if dt is not None:
            return dt

        name_lower = name.lower()

        # 2. Case-insensitive match against loaded doctypes — O(1)
        canonical = self._lower_index.get(name_lower)
        if canonical:
            cached = self._doctypes.get(canonical)
            if cached is not None:
                return cached
            # Stale index entry (points at a name no longer in _doctypes) —
            # self-heal rather than KeyError, and fall through to lazy-load.
            self._index_remove(canonical)

        # 3. Resolve against lazy known-names index — O(1)
        candidate = name if name in self._known_names else self._known_lower.get(name_lower)

        if candidate:
            dt = await self._lazy_load(candidate)
            if dt is not None:
                return dt

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("DocType “%(doctype)s” not found") % {"doctype": name},
        )

    async def get_meta(self, name: str) -> Meta | None:
        """Return the :class:`~grunt.document.meta.Meta` wrapper for *name*, or
        ``None`` if *name* isn't a registered DocType.

        The canonical, Frappe-``get_meta``-style accessor for callers that want
        field lookups, cached derived properties (``table``, ``get_valid_columns``,
        ...), or any other metadata query. Use :meth:`get` instead only when the
        raw pydantic :class:`DocType` model itself is required (compiling,
        syncing, editing the definition) — it still raises ``404`` on a miss.

        Unlike :meth:`get`, a missing DocType is not exceptional here — callers
        that need the old "404 if missing" behaviour raise it themselves after
        a ``None`` check, so the choice is explicit at each call site instead of
        implicit in this shared accessor.
        """
        from grunt.document.meta import Meta

        try:
            dt = await self.get(name)
        except HTTPException:
            return None
        return Meta(dt)

    async def get_or_none(self, name: str) -> DocType | None:
        """Like :meth:`get`, but returns ``None`` instead of raising 404.

        For call sites that need an existence check or an optional lookup
        without eagerly assuming the DocType is already in memory (core
        DocTypes are no longer guaranteed to be warm at boot — see
        :meth:`prefetch_names`).
        """
        try:
            return await self.get(name)
        except HTTPException:
            return None

    async def list_all(self) -> list[DocType]:
        """Return all registered DocTypes, loading any that are still lazy."""
        if self._known_names:
            # Load remaining lazy DocTypes so the list is complete
            from grunt.site.manager import site_manager

            try:
                site_name = site_manager.get_active_site()
                maker = site_manager.get_session_maker(site_name)
                async with maker() as session:
                    await self.load_all(session)
            except Exception as exc:
                log.warning("registry.list_all_lazy_failed", error=str(exc))

        return list(self._doctypes.values())

    # ── Write ────────────────────────────────────────────────────────────

    @staticmethod
    def _merge_core_fields(active_dt: DocType, doctype: DocType) -> list[DocField]:
        """Return fields present in the bundled JSON but missing from the stored definition."""
        stored_fieldnames = {f.fieldname for f in active_dt.fields}
        return [f for f in doctype.fields if f.fieldname not in stored_fieldnames]

    @staticmethod
    def _sync_core_doctype_attrs(active_dt: DocType, doctype: DocType) -> None:
        """Overwrite ``active_dt``'s always-synced top-level attrs from the JSON source.

        Only ``_CORE_SYNCED_DOCTYPE_ATTRS`` is touched — everything else (permissions,
        autoname, ...) is a Studio/user customization and is left as-is.
        """
        for attr in _CORE_SYNCED_DOCTYPE_ATTRS:
            json_val = getattr(doctype, attr, None)
            if json_val is not None and getattr(active_dt, attr, None) != json_val:
                setattr(active_dt, attr, json_val)

    @staticmethod
    def _sync_core_field_attrs(active_dt: DocType, doctype: DocType) -> None:
        """Overwrite each stored field's always-synced attrs from its JSON counterpart.

        Only ``_CORE_SYNCED_FIELD_ATTRS`` is touched, same rationale as
        :meth:`_sync_core_doctype_attrs`.
        """
        stored_fields = {f.fieldname: f for f in active_dt.fields}
        for json_field in doctype.fields:
            stored_field = stored_fields.get(json_field.fieldname)
            if stored_field is None:
                continue
            for attr in _CORE_SYNCED_FIELD_ATTRS:
                if getattr(stored_field, attr, None) != getattr(json_field, attr, None):
                    setattr(stored_field, attr, getattr(json_field, attr, None))

    @staticmethod
    def _reorder_core_fields(active_dt: DocType, doctype: DocType) -> None:
        """Position JSON-defined fields per JSON order; locally-added fields sort last."""
        json_order = {f.fieldname: i for i, f in enumerate(doctype.fields)}
        active_dt.fields.sort(key=lambda f: json_order.get(f.fieldname, 9999))

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
            select(GruntMetaDoctype).where(GruntMetaDoctype.c.name == doctype.name)
        )
        existing = existing_row.mappings().one_or_none()

        if existing:
            # Load the stored definition (preserves Studio customisations).
            try:
                active_dt = DocType.model_validate(existing["data"])
            except Exception:
                # Stored data is invalid — fall back to JSON and repair.
                log.warning(
                    "registry.core_stored_invalid",
                    name=doctype.name,
                    action="falling_back_to_json",
                )
                active_dt = doctype
                if sync_db:
                    await session.execute(
                        update(GruntMetaDoctype)
                        .where(GruntMetaDoctype.c.name == doctype.name)
                        .values(module=doctype.module, data=doctype.model_dump())
                    )
            else:
                # `permissions` is deliberately excluded from
                # _CORE_SYNCED_DOCTYPE_ATTRS (a Studio customisation, seeded
                # once and never overwritten automatically) — but that means
                # a permissions change committed to the JSON source silently
                # sits inert on every existing site until someone remembers
                # to run `grunt doctype sync <Name>`. Surface the drift
                # loudly instead of leaving it to be discovered by a random
                # test failure or an access-control gap nobody noticed.
                if [p.model_dump() for p in doctype.permissions] != [
                    p.model_dump() for p in active_dt.permissions
                ]:
                    log.warning(
                        "registry.core_permissions_drifted",
                        name=doctype.name,
                        hint=f"run `grunt doctype sync {doctype.name}` to apply",
                    )

                # Merge logic
                new_fields = self._merge_core_fields(active_dt, doctype)
                if new_fields:
                    active_dt.fields.extend(new_fields)
                    if sync_db:
                        log.info(
                            "registry.core_fields_merged",
                            name=doctype.name,
                            added=[f.fieldname for f in new_fields],
                        )

                self._sync_core_doctype_attrs(active_dt, doctype)
                self._sync_core_field_attrs(active_dt, doctype)
                self._reorder_core_fields(active_dt, doctype)

                if sync_db:
                    await session.execute(
                        update(GruntMetaDoctype)
                        .where(GruntMetaDoctype.c.name == doctype.name)
                        .values(module=doctype.module, data=active_dt.model_dump())
                    )
                    await session.flush()
        else:
            # First run: seed from the bundled JSON file.
            active_dt = doctype
            if sync_db:
                await session.execute(
                    insert(GruntMetaDoctype).values(
                        name=doctype.name,
                        module=doctype.module,
                        data=doctype.model_dump(),
                    )
                )
                await session.flush()

        self._doctypes[active_dt.name] = active_dt
        self._index_add(active_dt.name)
        if sync_db:
            log.info("registry.core_injected", name=active_dt.name)
        else:
            log.info("registry.core_loaded", name=active_dt.name)

    async def register(
        self,
        doctype: DocType,
        session: AsyncSession,
        async_engine: AsyncEngine,
    ) -> None:
        """Validate, persist, sync table, and cache a new DocType."""
        self._validate_new(doctype)

        # Registry may be partially lazy-loaded; always re-check DB uniqueness.
        existing = await session.scalar(
            select(GruntMetaDoctype.c.name).where(GruntMetaDoctype.c.name == doctype.name)
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_("DocType “%(doctype)s” already exists") % {"doctype": doctype.name},
            )

        # Persist to DB
        try:
            await session.execute(
                insert(GruntMetaDoctype).values(
                    name=doctype.name,
                    module=doctype.module,
                    data=doctype.model_dump(),
                )
            )
            await session.flush()
        except IntegrityError as exc:
            # DB-level fallback for race conditions / stale cache.
            if "grunt_meta_doctype.name" in str(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=_("DocType “%(doctype)s” already exists") % {"doctype": doctype.name},
                ) from exc
            raise

        # Create / update physical table (pass session to avoid SQLite locking)
        await sync_table(doctype, async_engine, session=session)

        # Cache
        self._doctypes[doctype.name] = doctype
        self._index_add(doctype.name)
        self._known_names.discard(doctype.name)
        self._known_index_remove(doctype.name)
        log.info("registry.registered", name=doctype.name)

    async def update(
        self,
        doctype: DocType,
        session: AsyncSession,
        async_engine: AsyncEngine,
    ) -> None:
        """Update an existing DocType, re-sync its table, refresh cache."""
        if doctype.name not in self._doctypes:
            # DocType may be known but not yet lazy-loaded — check DB before failing.
            exists = await session.scalar(
                select(GruntMetaDoctype.c.name).where(GruntMetaDoctype.c.name == doctype.name)
            )
            if not exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype.name},
                )
            await self._lazy_load(doctype.name)
        self._validate_fields(doctype)

        await session.execute(
            update(GruntMetaDoctype)
            .where(GruntMetaDoctype.c.name == doctype.name)
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
        log.info("registry.updated", name=doctype.name)

    async def delete(self, name: str, session: AsyncSession) -> None:
        """Remove DocType from registry and DB. Physical table is NOT dropped."""
        if name not in self._doctypes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("DocType “%(doctype)s” not found") % {"doctype": name},
            )
        await session.execute(delete(GruntMetaDoctype).where(GruntMetaDoctype.c.name == name))
        await session.flush()
        self._doctypes.pop(name, None)
        self._index_remove(name)
        self._known_names.discard(name)
        self._known_index_remove(name)
        invalidate_table_cache(name)
        invalidate_permission_cache(name)
        log.info("registry.deleted", name=name)

    # ── Validation helpers ───────────────────────────────────────────────

    def _validate_new(self, doctype: DocType) -> None:
        """Ensure name is unique and fields are valid."""
        if doctype.name in self._doctypes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_("DocType “%(doctype)s” already exists") % {"doctype": doctype.name},
            )
        self._validate_fields(doctype)

    @staticmethod
    def _validate_fields(doctype: DocType) -> None:
        """Check for duplicate, invalid, or oversized fieldnames."""
        seen: set[str] = set()
        for f in doctype.fields:
            if f.fieldname in seen:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_("Duplicate fieldname '%(fieldname)s' in DocType '%(name)s'")
                    % {"fieldname": f.fieldname, "name": doctype.name},
                )
            seen.add(f.fieldname)

            if not _FIELDNAME_RE.match(f.fieldname):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        _(
                            "Invalid fieldname '%(fieldname)s': "
                            "must start with a-z and contain only a-z, 0-9, _"
                        )
                        % {"fieldname": f.fieldname}
                    ),
                )
            if len(f.fieldname) > _MAX_FIELDNAME_LEN:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_("Fieldname '%(fieldname)s' exceeds %(max)s characters")
                    % {"fieldname": f.fieldname, "max": _MAX_FIELDNAME_LEN},
                )


# ── Per-site resolution ──────────────────────────────────────────────────
#
# One process can serve multiple sites (tenants), selected per-request via
# the ``current_site`` ContextVar (set by SiteContextMiddleware from the Host
# header). A DocType registry must never be shared across sites — the same
# name can mean a different definition per site. Instead of threading a site
# argument through every one of the ~70 call sites that do
# ``doctype_registry.get(...)``/``.list_all()``/``._doctypes...``, resolve
# the *instance* transparently through a proxy, keyed off the same
# ``current_site`` mechanism already used everywhere else (SiteManager's
# engines/session makers).

_registries: dict[str, DocTypeRegistry] = {}
_DEFAULT_KEY = "__no_site__"  # process has no ambient site concept at all


def _resolve_site_key() -> str:
    from grunt.site.manager import current_site, site_manager

    site = current_site.get()
    if site:
        return site
    try:
        return site_manager.get_active_site()
    except Exception:
        return _DEFAULT_KEY


def get_registry(site: str | None = None) -> DocTypeRegistry:
    """Return the DocTypeRegistry for *site* (or the ambient current site).

    Created lazily and cached, mirroring ``SiteManager.get_engine()``.
    """
    key = site or _resolve_site_key()
    reg = _registries.get(key)
    if reg is None:
        reg = DocTypeRegistry()
        _registries[key] = reg
    return reg


class _DocTypeRegistryProxy:
    """Forwards every attribute access to the current site's DocTypeRegistry.

    Keeps ``doctype_registry`` importable exactly as before at every existing
    call site — ``doctype_registry.get(...)``, ``.list_all()``, even direct
    ``._doctypes.clear()``/``[name] = x`` — while resolving which per-site
    instance backs the call freshly on every access.

    ``__delattr__`` forwards too, for the same reason ``__setattr__`` does:
    ``unittest.mock.patch("...doctype_registry.get", ...)`` sets the mock via
    ``setattr`` (forwarded onto the real registry instance, shadowing its
    class method) but decides at teardown — based on whether "get" was ever
    in *this proxy's own* ``__dict__``, which it never is — to restore via
    ``delattr`` rather than ``setattr``. Without forwarding that delete too,
    teardown raises ``AttributeError`` on the proxy instead of removing the
    shadowing attribute from the real registry object.
    """

    def __getattr__(self, item):
        return getattr(get_registry(), item)

    def __delattr__(self, item):
        delattr(get_registry(), item)

    def __setattr__(self, item, value):
        setattr(get_registry(), item, value)

    def __repr__(self) -> str:
        return f"<doctype_registry proxy -> {get_registry()!r}>"


doctype_registry = _DocTypeRegistryProxy()
