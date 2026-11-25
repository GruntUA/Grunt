"""The document pipeline every controller runs, whatever stores its documents.

Insert, update and delete fire the document events, validate the values,
check permissions and workflow and run the controller's lifecycle hooks; the
storage itself is the DocType's :class:`~grunt.store.Store` (``store_for``):
the table by default, or what the controller names in ``store_class``. What
the store can't do (``capabilities``) is refused before any hook runs; the
side effects - search index, webhooks, versions - follow the same pipeline for
every store.
"""

import copy
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
from grunt.document.serde import audit_fields, same_instant
from grunt.document.update_side_effects import (
    fire_delete_services,
    fire_update_services,
    record_update_changes,
)
from grunt.document.validation import _validate_data, refuse_set_once_changes, validate_child_rows
from grunt.errors import ApplicationError, not_found, stale_document
from grunt.events import fire
from grunt.i18n import _
from grunt.local import require_session_user, session_user, stamp_user
from grunt.log import log
from grunt.monitoring import perf
from grunt.naming.service import naming_service
from grunt.permissions import audit
from grunt.permissions.query import reference_readable
from grunt.permissions.rbac import permission_checker
from grunt.permissions.roles import role_access
from grunt.query.query import Query
from grunt.search.service import search_index_service
from grunt.site.settings import get_system_settings
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

    def _bind(self) -> None:
        """Provided by :class:`Document`: session/engine from the active context."""

    def _set_grunt_context(self) -> tuple:  # type: ignore[empty-body]
        """Provided by :class:`Document`: bind its session/engine for the hooks."""

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None:
        """Provided by :class:`Document`: undo :meth:`_set_grunt_context`."""

    def _wrap_children(self, only: str | None = None) -> None:
        """Provided by :class:`Document`: child rows as child documents."""

    def _unwrap_children(self) -> None:
        """Provided by :class:`Document`: child documents back to their rows."""

    def _rows(self) -> dict[str, Any]:  # type: ignore[empty-body]
        """Provided by :class:`Document`: ``self.data`` with child rows as dicts."""

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
        """Return the freshest DocType definition, forcing a lazy reload if needed.

        Also reads the (cached) site settings: value coercion is sync and rounds
        numbers by the site's rounding_method (grunt.utils.numbers), which this
        read keeps current for the save that follows."""
        await get_system_settings()

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

        The hooks see child rows as documents of the child controller; the
        pipeline around them, rows.
        """
        self._wrap_children()
        try:
            for hook_name in hook_names:
                await getattr(self, hook_name)()
        except ApplicationError as e:
            raise e.to_api_error() from e
        finally:
            self._unwrap_children()

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

    async def _fire_write_hooks(self, primary_event: str, doc: dict[str, Any]) -> None:
        """Fire the two hook events that follow a successful insert/update."""
        for event in (primary_event, "after_save"):
            await fire(
                event, doctype=self.doctype, doc=doc, user=session_user(), session=self.session
            )

    async def _load_existing(self, doc_id: str | None) -> dict[str, Any]:
        """The stored document *doc_id*, read like ``grunt.get_doc`` reads it
        (``Document`` implements it - this mixin can't import the loader)."""
        raise NotImplementedError

    async def _build_initial_row(
        self, dt: Any, data: dict[str, Any], now: datetime
    ) -> dict[str, Any]:
        """The new document: name, audit fields, coerced values and workflow state."""
        user = require_session_user()
        # Rule -> caller's name (not for a counter series) -> controller's
        # autoname() -> the DocType's autoname: grunt.naming.service.new_name.
        custom_autoname: Callable[..., Awaitable[str]] | None = getattr(
            type(self), "autoname", None
        )
        doc_name = await naming_service.new_name(
            dt,
            data,
            self.session,
            controller_autoname=custom_autoname if callable(custom_autoname) else None,
        )

        columns = self._store.columns
        row: dict[str, Any] = (
            {}
            if columns is not None
            else {k: v for k, v in data.items() if k[:2] != "__" and k != "doctype"}
        )
        standard: dict[str, Any] = {"name": doc_name, **audit_fields(stamp_user(user), now)}
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
        data = strip_file_signatures(self._rows())
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
            await permission_checker.require_in_scope(dt, "create", self.data, user=user)
            await self._before_store(dt)
            self.data = await store.insert(self.data, input=data, user=stamp_user(user))
            log.info("document.created", doctype=self.doctype, id=self.data.get("name"))
            await audit.record(
                self.session,
                self.doctype,
                str(self.data.get("name")),
                None,
                self.data,
                stamp_user(user),
            )
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
        data = strip_file_signatures(plain(data))
        # Optimistic locking: the `modified_at` the edit was based on - sent
        # explicitly by offline replays, otherwise the one the document carries
        # (the form and ``doc.save()`` send the whole document). A newer stored
        # copy -> 409. A partial payload without it is guarded only against a
        # write between the load below and the UPDATE (SqlStore.update).
        base_modified_at = data.pop("__base_modified_at", None) or data.get("modified_at")
        dt = self._dt = await self._resolve_dt(self.doctype)

        # A singleton's first save arrives here, not at ``insert`` - the form
        # always routes it as an update (``doc_id`` == DocType name) because
        # there is no separate "new" state. Upsert: if the sole row does not
        # exist yet, create it now (named after the DocType).
        store = self._store_for(dt)
        if dt.is_singleton and not await self._singleton_exists(dt, store):
            self.data = {**data, "name": dt.name}  # rows: _update's data
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
            and not same_instant(base_modified_at, existing.get("modified_at"))
        ):
            raise stale_document()

        # Workflow: the state moves only by transitions; an edit may itself be
        # an `on_edit` transition (then *data* carries the new state).
        data = dict(data)
        scopes = await pipeline.begin_update(self.doctype, existing, data, user)
        await check_write("update", self.doctype, existing, data, user)
        await self._refuse_hidden_writes(dt, user, data, existing)
        refuse_set_once_changes(dt, data, existing, user)

        errors = _validate_data(dt, data, partial=True, ignore_required=ignore_required)
        errors += await validate_child_rows(dt, data, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        update_data = update_values(dt, data, store.columns, stamp_user(user))
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
        # The stored row was checked before the change; the new one must stay in scope.
        await permission_checker.require_in_scope(dt, "write", self.data, user=user)
        await self._before_store(dt)
        result = await store.update(
            real_id, self.data, before=existing, input=data, user=stamp_user(user)
        )
        log.info("document.updated", doctype=self.doctype, id=real_id)
        # Access changes are logged whatever the store keeps of history.
        await audit.record(self.session, self.doctype, real_id, existing, result, stamp_user(user))

        if store.can(HISTORY):
            await record_update_changes(
                session=self.session,
                engine=self.engine,
                doctype_name=self.doctype,
                real_id=real_id,
                dt=dt,
                existing=existing,
                result=result,
                user=stamp_user(user),
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
        # What was stored - a before_delete hook may change ``self.data`` (the same dict).
        stored = copy.deepcopy(existing) if audit.is_audited(self.doctype) else existing
        tokens = self._set_grunt_context()
        try:
            await self._run_lifecycle_hooks("before_delete")
            await store.delete(real_id, before=existing)
            await audit.record(self.session, self.doctype, real_id, stored, None, stamp_user(user))
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


def _has_documents(data: dict[str, Any]) -> bool:
    return any(
        type(value) is list and any(isinstance(v, DocumentLifecycleMixin) for v in value)
        for value in data.values()
    )


def row_of(value: Any) -> Any:
    """A child document as its row dict - the document's own ``data``, or a copy
    of it when it holds child documents of its own."""
    if isinstance(value, DocumentLifecycleMixin):
        data = value.data
        return plain(data) if _has_documents(data) else data
    return value


def plain(data: dict[str, Any]) -> dict[str, Any]:
    """A shallow copy of *data* with child documents as their row dicts - the
    rows themselves are not copied."""
    return {
        key: [row_of(v) for v in value]
        if type(value) is list and any(isinstance(v, DocumentLifecycleMixin) for v in value)
        else value
        for key, value in data.items()
    }
