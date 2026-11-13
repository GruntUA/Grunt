"""The document pipeline every controller runs, whatever stores its documents.

Insert, update and delete fire the document events, validate the values,
check permissions and workflow and run the controller's lifecycle hooks; the
storage itself is the DocType's :class:`~grunt.store.Store` (``store_for``):
the table by default, or what the controller names in ``store_class``. What
the store can't do (``capabilities``) is refused before any hook runs; the
side effects - search index, webhooks, versions - follow the same pipeline for
every store.
"""

import functools
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Concatenate

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from grunt.db.errors import friendly_integrity_error
from grunt.document import pipeline
from grunt.document.fetch import apply_fetch_from
from grunt.document.formula import compute_formulas
from grunt.document.guards import check_write
from grunt.document.payload import update_values
from grunt.document.relations import apply_field_values
from grunt.document.serde import audit_fields
from grunt.document.update_side_effects import (
    fire_delete_services,
    fire_update_services,
    record_update_changes,
)
from grunt.document.validation import _validate_data, validate_child_rows
from grunt.errors import ApplicationError, not_found
from grunt.events import fire
from grunt.i18n import _
from grunt.local import require_session_user
from grunt.log import log
from grunt.monitoring import perf
from grunt.naming.patterns import has_counter, parse_pattern
from grunt.naming.service import naming_service
from grunt.permissions.query import reference_readable
from grunt.permissions.rbac import permission_checker
from grunt.permissions.roles import role_access
from grunt.permissions.user_permissions import doc_violation
from grunt.query.query import Query
from grunt.search.service import search_index_service
from grunt.storage.references import release_dropped_files
from grunt.storage.signing import strip_file_signatures
from grunt.store.base import DELETE, HISTORY, INSERT, REFERENCES, UPDATE, Store
from grunt.store.lookup import store_for
lazy from grunt.document.collection import repoint_references, validate_replacement
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.registry import doctype_registry

type _Pipeline[**P, R] = Callable[Concatenate[Any, P], Awaitable[R]]


def _timed[**P, R](op: str) -> Callable[[_Pipeline[P, R]], _Pipeline[P, R]]:
    """Record the pipeline in perf stats as ``Document <op>`` of the DocType.

    On the pipeline itself, not on ``insert``/``save``/``delete``: the REST API
    and ``grunt.new_doc`` call the pipelines directly.
    """

    def decorator(fn: _Pipeline[P, R]) -> _Pipeline[P, R]:
        @functools.wraps(fn)
        async def wrapper(self: Any, /, *args: P.args, **kwargs: P.kwargs) -> R:
            with perf.measure("Document", op, self.doctype):
                return await fn(self, *args, **kwargs)

        return wrapper

    return decorator


class DocumentLifecycleMixin:
    doctype: str
    data: dict[str, Any]
    session: Any
    engine: Any
    # Set while a pipeline runs: the DocType meta, the values as the caller
    # gave them (on update - only the changes), and (update/delete) the stored
    # document before the change.
    _dt: Any
    _store: Store
    input_data: dict[str, Any]
    doc_before_save: dict[str, Any] | None

    def _bind(self) -> None: ...
    @classmethod
    async def load(  # type: ignore[empty-body]  # Document.load
        cls,
        doctype: str,
        name: str | None = None,
        *,
        expand: list[str] | None = None,
        session: Any = None,
        engine: Any = None,
    ) -> Any: ...
    @property
    def user(self) -> str | None: ...  # type: ignore[empty-body]  # Document: the session user

    def _set_grunt_context(self) -> tuple: ...  # type: ignore[empty-body]
    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None: ...

    # Pipeline steps

    def _store_for(self, dt: Any) -> Store:
        """The store of *dt*, kept for the rest of the pipeline."""
        self._store = store_for(dt, self.session)
        return self._store

    async def _singleton_exists(self, dt: Any, store: Store) -> bool:
        return await store.count(Query(dt.name)) > 0

    async def _before_store(self, dt: Any) -> None:
        """Last changes to ``self.data`` after the hooks, before it is stored:
        a web page's route, computed fields."""
        await pipeline.before_store(dt, self.data, self.session)
        await compute_formulas(dt.doc, self.data)

    async def _repoint_references(
        self, dt: Any, store: Store, real_id: str, replace_with: str
    ) -> None:
        if not store.can(REFERENCES):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("“%(doctype)s” does not support replacing references")
                % {"doctype": self.doctype},
            )
        await validate_replacement(self.session, dt, real_id, replace_with)
        try:
            await repoint_references(
                self.session, dt, self.doctype, real_id, replace_with, is_merge=True
            )
            await self.session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_("Could not reassign the links: uniqueness conflict"),
            ) from exc

    # Pipeline

    async def _resolve_dt(self, doctype_name: str) -> Any:
        """Return the freshest DocType definition, forcing a lazy reload if needed."""

        fresh = await doctype_registry._lazy_load(doctype_name)
        if fresh is not None:
            return Meta(fresh)
        dt = await doctype_registry.get_meta(doctype_name)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype_name})
        return dt

    async def _run_lifecycle_hooks(self, *hook_names: str) -> None:
        """Call the named controller lifecycle hooks, in order.

        A ``throw()`` from any hook becomes an HTTP error with the status
        its code maps to - the one place that translates "controller rejected
        the save" into HTTP, shared by insert/update/delete.
        """
        try:
            for hook_name in hook_names:
                await getattr(self, hook_name)()
        except ApplicationError as e:
            raise e.to_api_error() from e

    @staticmethod
    async def _refuse_hidden_writes(
        dt: Any, user: str | None, data: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> None:
        """403 when *data* sets a field hidden from *user* - read-hidden means
        write-hidden too, or a hidden value could be overwritten blind - or
        changes one that is read-only for them on an existing document."""
        changed = (await role_access(dt, user)).forbidden_changes(data, existing)
        if changed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_("Not permitted to change fields: %(fields)s")
                % {"fields": ", ".join(sorted(dt.get_label(f) for f in changed))},
            )

    @staticmethod
    async def _require_user_permissions(dt: Any, row: dict[str, Any], user: str | None) -> None:
        """403 when the values being written fall outside *user*'s User
        Permissions - the role check alone only looks at the stored row, so
        without this a restricted user could create a record in (or move one
        to) a scope they may not touch."""
        fieldname = await doc_violation(user, dt, row)
        if fieldname is None:
            return
        label = _(dt.get_label(fieldname)) if fieldname else _(dt.doc.label or dt.doc.name)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_("No access: “%(field)s” is outside your user permissions") % {"field": label},
        )

    async def _fire_write_hooks(self, primary_event: str, doc: dict[str, Any]) -> None:
        """Fire the two hook events that follow a successful insert/update."""
        for event in (primary_event, "after_save"):
            await fire(event, doctype=self.doctype, doc=doc, user=self.user, session=self.session)

    async def _load_existing(self, doc_id: str | None) -> dict[str, Any]:
        """The stored document *doc_id*, read like ``grunt.get_doc`` reads it."""

        doc = await self.load(self.doctype, doc_id, session=self.session, engine=self.engine)
        return doc.data

    async def _build_initial_row(
        self, dt: Any, data: dict[str, Any], now: datetime
    ) -> dict[str, Any]:
        """The new document: name, audit fields, coerced values and workflow state."""
        user = require_session_user()
        # An explicit caller-supplied name wins over autoname for fixtures and
        # imports, which rely on stable names regardless of the DocType's
        # naming scheme - but NOT for counter-based series (e.g.
        # "ВХ-.YYYY.-.####"), where the counter is the source of truth and
        # must always be consulted. Otherwise any caller (a frontend bug, a
        # crafted API request) could pass an arbitrary `name` and silently
        # hijack the series - the counter would never advance and a later,
        # properly-generated name could collide with it.
        pattern = (dt.autoname or "").removeprefix("format:")
        if data.get("name") and not has_counter(parse_pattern(pattern)):
            doc_name = str(data["name"])
        else:
            custom_autoname: Callable[..., Awaitable[str]] | None = getattr(
                type(self), "autoname", None
            )
            if custom_autoname is not None and callable(custom_autoname):
                doc_name = await custom_autoname(data, self.session)
            else:
                doc_name = await naming_service.generate(dt.autoname or "", data, self.session)

        columns = self._store.columns
        row: dict[str, Any] = (
            {}
            if columns is not None
            else {k: v for k, v in data.items() if k[:2] != "__" and k != "doctype"}
        )
        standard: dict[str, Any] = {"name": doc_name, **audit_fields(user, now)}
        for k, v in standard.items():
            if columns is None or k in columns:
                row[k] = v

        apply_field_values(dt.fields, data, row)
        # Submitted MultiLink lists, so lifecycle hooks see them (persisted from *data*).
        for f in dt.get_multilink_fields():
            if f.fieldname in data:
                row[f.fieldname] = data[f.fieldname]

        await pipeline.prepare_insert(dt, data, row, user)
        return row

    @_timed("insert")
    async def _insert(self, *, ignore_required: bool = False) -> dict[str, Any]:
        """Create ``self.data`` as a new document - the insert pipeline.

        The single entry point for creating a document - ``grunt.new_doc``
        calls it too, so global/DocType hooks (notifications, assignment rules,
        backlink sync, activity log) fire identically regardless of the caller.
        """
        self._bind()
        user = require_session_user()
        data = strip_file_signatures(self.data)
        await fire(
            "before_save", doctype=self.doctype, doc=dict(data), user=user, session=self.session
        )

        dt = self._dt = await self._resolve_dt(self.doctype)
        store = self._store_for(dt)
        if not store.can(INSERT):
            raise store.unsupported()
        if dt.is_singleton and await self._singleton_exists(dt, store):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_("'%(name)s' is a singleton.") % {"name": dt.name},
            )

        errors = _validate_data(dt, data, ignore_required=ignore_required)
        errors += await validate_child_rows(dt, data, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        await self._refuse_hidden_writes(dt, user, data)

        # A comment / tag / attachment may only be added to a readable document.
        if (
            not (await role_access(dt, user)).is_unrestricted
            and await reference_readable(user, dt, data) is False
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=_("No access to the document")
            )

        self.input_data = data
        self.data = await self._build_initial_row(dt, data, datetime.now(UTC))
        # As on update: hooks see the submitted child rows and MultiLink lists,
        # and their in-place changes are persisted (the store writes them from *data*).
        for f in [*dt.get_child_table_fields(), *dt.get_multilink_fields()]:
            if f.fieldname in data:
                self.data[f.fieldname] = data[f.fieldname]

        tokens = self._set_grunt_context()
        try:
            await apply_fetch_from(dt.doc, self.data)
            await self._run_lifecycle_hooks("validate", "before_insert", "before_save")
            await self._require_user_permissions(dt, self.data, user)
            await permission_checker.require_in_scope(dt, "create", self.data, user=user)
            await self._before_store(dt)
            self.data = await store.insert(self.data, input=data, user=user)
            log.info("document.created", doctype=self.doctype, id=self.data.get("name"))
            await self._run_lifecycle_hooks("after_insert", "after_save")
            await search_index_service.index_document(self.session, self.doctype, dt.doc, self.data)
            await pipeline.after_write("after_insert", self.session, self.doctype, self.data)
        except IntegrityError as exc:
            raise friendly_integrity_error(exc, dt.doc, self.session) from exc
        finally:
            self._reset_grunt_context(tokens)

        created = await store.output(self.data)
        self.data = created
        await self._fire_write_hooks("after_insert", created)
        return created

    @_timed("save")
    async def _update(
        self, doc_id: str, data: dict[str, Any], *, ignore_required: bool = False
    ) -> dict[str, Any]:
        """Apply the changes *data* to the stored document *doc_id* - the update pipeline.

        Single entry point for updating a document - see :meth:`_insert`.
        """
        self._bind()
        user = require_session_user()
        data = strip_file_signatures(data)
        # Optimistic-concurrency guard: the `modified_at` the client's edit was
        # based on (sent by offline replays). A newer server copy -> 409.
        base_modified_at = data.pop("__base_modified_at", None)
        dt = self._dt = await self._resolve_dt(self.doctype)

        # A singleton's first save arrives here, not at ``insert`` - the form
        # always routes it as an update (``doc_id`` == DocType name) because
        # there is no separate "new" state. Upsert: if the sole row does not
        # exist yet, create it now (named after the DocType).
        store = self._store_for(dt)
        if dt.is_singleton and not await self._singleton_exists(dt, store):
            self.data = {**data, "name": dt.name}
            return await self._insert(ignore_required=ignore_required)

        await fire(
            "before_save",
            doctype=self.doctype,
            doc={"id": doc_id, **data},
            user=user,
            session=self.session,
        )

        if not store.can(UPDATE):
            raise store.unsupported()
        existing = await self._load_existing(doc_id)

        # write_guard() (the facade's pre-check) only verifies doctype-level
        # access - it calls permission_checker with doc=None, so a
        # `match`-restricted write permission (e.g. "owner == user") is never
        # evaluated there. `existing` is already fetched for the diff logic
        # below, so this row-level check is free - no extra DB round trip.
        await permission_checker.require(dt, "write", existing, user=user)

        if (
            base_modified_at
            and existing.get("modified_at") is not None
            and not _same_instant(base_modified_at, existing.get("modified_at"))
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_(
                    "The document was changed after you started editing. "
                    "Open it again and repeat your changes."
                ),
            )

        # Workflow: the state moves only by transitions; an edit may itself be
        # an `on_edit` transition (then *data* carries the new state).
        data = dict(data)
        scopes = await pipeline.begin_update(self.doctype, existing, data, user)
        await check_write("update", self.doctype, existing, data, user)
        await self._refuse_hidden_writes(dt, user, data, existing)

        errors = _validate_data(dt, data, partial=True, ignore_required=ignore_required)
        errors += await validate_child_rows(dt, data, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        update_data = update_values(dt, data, store.columns, user)
        real_id = existing["name"]
        merged = {**existing, **update_data}
        # Inject submitted child-table rows into merged so lifecycle hooks see the
        # incoming data (not the old DB rows) and their mutations are persisted.
        # MultiLink lists too - visible to hooks, persisted from *data*.
        for f in [*dt.get_child_table_fields(), *dt.get_multilink_fields()]:
            if f.fieldname in data:
                merged[f.fieldname] = data[f.fieldname]

        self.input_data = data
        self.doc_before_save = existing
        self.data = merged

        tokens = self._set_grunt_context()
        try:
            with scopes.active():
                result = await self._store_update(dt, store, existing, data, real_id, user)
        except IntegrityError as exc:
            raise friendly_integrity_error(exc, dt.doc, self.session) from exc
        finally:
            self._reset_grunt_context(tokens)

        await scopes.finish(result, user, self.session)
        return result

    async def _store_update(
        self,
        dt: Any,
        store: Store,
        existing: dict[str, Any],
        data: dict[str, Any],
        real_id: str,
        user: str,
    ) -> dict[str, Any]:
        """The update from the hooks on: store it, record it, tell the services."""
        await apply_fetch_from(dt.doc, self.data, existing)
        await self._run_lifecycle_hooks("validate", "before_save")
        await self._require_user_permissions(dt, self.data, user)
        # The stored row was checked before the change; the new one must stay in scope.
        await permission_checker.require_in_scope(dt, "write", self.data, user=user)
        await self._before_store(dt)
        result = await store.update(real_id, self.data, before=existing, input=data, user=user)
        log.info("document.updated", doctype=self.doctype, id=real_id)

        if store.can(HISTORY):
            await record_update_changes(
                session=self.session,
                engine=self.engine,
                doctype_name=self.doctype,
                real_id=real_id,
                dt=dt,
                existing=existing,
                result=result,
                user=user,
            )
        await release_dropped_files(self.doctype, existing, result)

        self.data = result
        await self._run_lifecycle_hooks("after_save")

        await fire_update_services(
            session=self.session, doctype_name=self.doctype, dt=dt.doc, result=result
        )
        await self._fire_write_hooks("after_update", result)
        return result

    @_timed("delete")
    async def _delete(self, *, replace_with: str | None = None) -> None:
        """Delete the stored document ``self.name`` - the delete pipeline.

        Single entry point for deleting a document - see :meth:`_insert`.

        ``replace_with`` - id of a surviving document (same DocType) that every
        reference to the deleted document is repointed to before it is removed.
        """
        self._bind()
        user = require_session_user()
        doc_id = self.data.get("name")
        if doc_id is None:
            raise ValueError(f"Cannot delete {self.doctype}: document has no name")
        dt = self._dt = await self._resolve_dt(self.doctype)
        store = self._store_for(dt)
        if not store.can(DELETE):
            raise store.unsupported()

        existing = await self._load_existing(str(doc_id))

        # Same reasoning as update(): write_guard()'s pre-check can't see
        # `match`-restricted delete permissions (doc=None there); this reuses
        # the `existing` fetch already needed below, so it's free.
        await permission_checker.require(dt, "delete", existing, user=user)

        await pipeline.check_delete(self.doctype, existing, user)
        await check_write("delete", self.doctype, existing, {}, user)

        real_id = existing["name"]

        if replace_with:
            await self._repoint_references(dt, store, real_id, replace_with)

        await fire(
            "before_delete", doctype=self.doctype, doc=existing, user=user, session=self.session
        )

        self.doc_before_save = existing
        self.data = existing
        tokens = self._set_grunt_context()
        try:
            await self._run_lifecycle_hooks("before_delete")
            await store.delete(real_id, before=existing)
            await fire_delete_services(
                session=self.session, doctype_name=self.doctype, real_id=real_id, existing=existing
            )
            await self._run_lifecycle_hooks("after_delete")
        finally:
            self._reset_grunt_context(tokens)

        await fire(
            "after_delete",
            doctype=self.doctype,
            doc_id=real_id,
            doc=existing,
            user=user,
            session=self.session,
        )


def _same_instant(a: Any, b: Any) -> bool:
    """Compare two timestamps given as datetimes or ISO strings (``Z`` / offset / naive-UTC)."""

    def parse(v: Any) -> datetime | None:
        if isinstance(v, datetime):
            dt = v
        elif isinstance(v, str) and v:
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    pa, pb = parse(a), parse(b)
    return pa is not None and pb is not None and pa == pb
