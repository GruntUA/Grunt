"""Write-side mixin for the Document pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from grunt import _, log

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine

    from grunt.auth.doctypes.User.user import User

import grunt
from grunt.db.errors import friendly_integrity_error
from grunt.document.aggregate import compute_aggregations
from grunt.document.formula import compute_formulas
from grunt.document.meta import Meta
from grunt.document.mixins.read import DocumentReadMixin
from grunt.document.registry import document_registry
from grunt.document.relations import (
    _load_child_tables,
    _save_child_tables,
    apply_field_values,
    attach_multi_link_values,
)
from grunt.document.serde import audit_fields, serialize_datetimes
from grunt.document.update_side_effects import (
    delete_row_and_links,
    fire_delete_services,
    fire_update_services,
    record_update_changes,
)
from grunt.document.validation import _validate_data
from grunt.document.virtual import (
    is_virtual_routed,
    virtual_create,
    virtual_delete,
    virtual_update,
)
from grunt.errors import ApplicationError, not_found
from grunt.events import fire
from grunt.metadata.registry import doctype_registry
from grunt.naming import naming_service
from grunt.naming.patterns import has_counter, parse_pattern
from grunt.permissions.access import RoleAccess
from grunt.permissions.rbac import permission_checker
from grunt.permissions.reference import reference_readable
from grunt.permissions.user_permissions import doc_violation
from grunt.search.service import search_index_service
from grunt.storage.signing import strip_file_signatures
from grunt.webhook.service import webhook_service
from grunt.website.generator import fill_route
from grunt.workflow.engine import _active
from grunt.workflow.guard import check_delete, check_update
from grunt.workflow.registry import get_active_workflow

PROTECTED_FIELDS = frozenset({"name", "owner", "created_at"})


class DocumentWriteMixin(DocumentReadMixin):
    """Write half of the Document pipeline.

    Extends :class:`DocumentReadMixin` because every write operation needs to
    read the current row first (``get_document`` - for update's ``existing``,
    delete's pre-delete snapshot, etc.). Inheriting directly means there is one
    fixed method resolution order, not an implicit one that depends on the
    order ``Document`` lists its base classes in.
    """

    engine: AsyncEngine

    def _set_grunt_context(self, user: User) -> tuple:  # type: ignore[empty-body]
        ...

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None: ...

    async def _resolve_dt(self, doctype_name: str) -> Any:
        """Return the freshest DocType definition, forcing a lazy reload if needed."""
        fresh = await doctype_registry._lazy_load(doctype_name)
        if fresh is not None:
            return Meta(fresh)
        dt = await grunt.get_meta(doctype_name)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype_name})
        return dt

    async def _run_lifecycle_hooks(self, doc: Any, *hook_names: str) -> None:
        """Call the named controller lifecycle hooks on *doc*, in order.

        A ``grunt.throw()`` from any hook becomes an HTTP error with the status
        its code maps to - the one place that translates "controller rejected
        the save" into HTTP, shared by create/update/delete.
        """
        try:
            for hook_name in hook_names:
                await getattr(doc, hook_name)()
        except ApplicationError as e:
            raise e.to_api_error() from e

    @staticmethod
    async def _require_user_permissions(dt: Any, row: dict[str, Any], user: User) -> None:
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

    async def _fire_write_hooks(
        self,
        primary_event: str,
        secondary_event: str,
        doctype_name: str,
        doc: dict[str, Any],
        user: User,
    ) -> None:
        """Fire the two hook events that follow a successful create/update."""
        await fire(primary_event, doctype=doctype_name, doc=doc, user=user, session=self.session)
        await fire(secondary_event, doctype=doctype_name, doc=doc, user=user, session=self.session)

    # Create

    # create helpers

    async def _check_singleton(self, dt: Any, table: Any) -> None:
        """Raise 409 if the DocType is a singleton and a document already exists."""
        if not dt.is_singleton:
            return
        existing = await self.session.execute(select(func.count()).select_from(table))
        if (existing.scalar() or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_("'%(name)s' is a singleton.") % {"name": dt.name},
            )

    async def _build_initial_row(
        self,
        dt: Any,
        table: Any,
        data: dict[str, Any],
        user: User,
        now: datetime,
    ) -> tuple[str, dict[str, Any]]:
        """Assemble the initial DB row dict (standard fields + DocType fields + workflow).

        Returns ``(doc_id, row)``.
        """
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
            controller_cls = document_registry.get(dt.name)
            custom_autoname: Callable[..., Awaitable[str]] | None = getattr(
                controller_cls, "autoname", None
            )
            if custom_autoname is not None and callable(custom_autoname):
                doc_name = await custom_autoname(data, self.session)
            else:
                doc_name = await naming_service.generate(dt.autoname or "", data, self.session)

        row: dict[str, Any] = {}
        standard: dict[str, Any] = {"name": doc_name, **audit_fields(user.email, now)}
        for k, v in standard.items():
            if k in table.c:
                row[k] = v

        apply_field_values(dt.fields, data, row)
        # Submitted MultiLink lists, so lifecycle hooks see them (persisted from *data*).
        for f in dt.get_multilink_fields():
            if f.fieldname in data:
                row[f.fieldname] = data[f.fieldname]

        workflow = await get_active_workflow(dt.name)
        if workflow:
            from grunt.workflow.guard import check_create

            await check_create(dt.name, data, user)
            sf = workflow.state_field
            if sf in data:
                row[sf] = data[sf]
            elif sf not in row:
                initial = next((s for s in workflow.states if s.is_initial), None)
                if initial:
                    row[sf] = initial.state
                    target = dt.get_field(initial.update_field or "")
                    if target is not None and target.fieldname not in data:
                        row[target.fieldname] = target.coerce(initial.update_value)

        return doc_name, row

    async def _persist_new_doc(
        self,
        dt: Any,
        table: Any,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
        row: dict[str, Any],
        user: User,
        now: datetime,
    ) -> None:
        """Run create pipeline: hooks -> insert -> children -> aggregates -> links -> hooks."""
        controller_cls = document_registry.get(doctype_name)
        doc = controller_cls(doctype_name, row, user, self.session)

        await self._run_lifecycle_hooks(doc, "validate", "before_insert", "before_save")
        await self._require_user_permissions(dt, row, user)
        await fill_route(dt, row, self.session)
        await compute_formulas(dt.doc, row)
        await self._insert_row(table, row)
        await self._save_children(dt, doc_id, data, user, now)
        await self._apply_aggregations(dt, table, doc_id, row)
        await self._sync_multi_links(dt, doctype_name, doc_id, data)

        log.info("document.created", doctype=doctype_name, id=doc_id)
        await self._run_lifecycle_hooks(doc, "after_insert", "after_save")

    async def _insert_row(self, table: Any, row: dict[str, Any]) -> None:
        """Insert main document row and flush to materialize DB state before child writes."""
        table_cols = {c.name for c in table.c}
        db_row = {k: v for k, v in row.items() if k in table_cols}
        await self.session.execute(table.insert().values(**db_row))
        await self.session.flush()

    async def _save_children(
        self,
        dt: Any,
        doc_id: str,
        data: dict[str, Any],
        user: User,
        now: datetime,
    ) -> None:
        """Persist child-table rows for the created document."""
        await _save_child_tables(self.session, dt.doc, doc_id, data, user, now)

    async def _apply_aggregations(
        self,
        dt: Any,
        table: Any,
        doc_id: str,
        row: dict[str, Any],
    ) -> None:
        """Compute and persist aggregate fields derived from child tables."""
        agg_values = await compute_aggregations(self.session, dt.doc, doc_id)
        if not agg_values:
            return

        await self.session.execute(
            table.update().where(table.c.name == doc_id).values(**agg_values)
        )
        row.update(agg_values)
        await self.session.flush()

    async def _sync_multi_links(
        self,
        dt: Any,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        only_present: bool = False,
    ) -> None:
        """Persist values for MultiLink virtual relation fields.

        With ``only_present=True`` fields absent from *data* are left untouched
        (used on update so unmentioned relations are preserved).
        """
        for mlf in dt.get_multilink_fields():
            if only_present and mlf.fieldname not in data:
                continue
            values = data.get(mlf.fieldname)
            if isinstance(values, list):
                await self._ml.set_values(
                    doctype_name,
                    doc_id,
                    mlf.fieldname,
                    mlf.options or "",
                    values,
                )

    async def _fire_create_services(self, doctype_name: str, dt: Any, row: dict[str, Any]) -> None:
        """Update the search index and fire outgoing webhooks after a successful insert."""
        await search_index_service.index_document(self.session, doctype_name, dt.doc, row)
        await webhook_service.fire(self.session, "after_insert", doctype_name, row)

    async def _serialize_doc_out(
        self, doctype_name: str, doc_id: str, row: dict[str, Any], dt: Any
    ) -> dict[str, Any]:
        """Serialise datetime values and attach MultiLink field values for the response."""
        serialize_datetimes(row)
        await attach_multi_link_values(self._ml, doctype_name, doc_id, dt.doc, row)
        return row

    # Create

    async def create_document(
        self,
        doctype_name: str,
        data: dict[str, Any],
        user: User,
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        """Run the full create pipeline: hooks -> validate -> insert -> hooks.

        This is the single entry point for creating a document - both the
        ``grunt_app.new_doc`` facade and ``Document.insert()`` call through here,
        so global/DocType hooks (notifications, assignment rules, backlink sync,
        activity log) fire identically regardless of the caller.
        """
        data = strip_file_signatures(data)
        await fire(
            "before_save", doctype=doctype_name, doc=dict(data), user=user, session=self.session
        )

        dt = await self._resolve_dt(doctype_name)
        if is_virtual_routed(dt, doctype_name):
            created = await virtual_create(doctype_name, user, data)
            await self._fire_write_hooks("after_insert", "after_save", doctype_name, created, user)
            return created

        table = dt.table
        await self._check_singleton(dt, table)

        errors = _validate_data(dt, data, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        # A comment / tag / attachment may only be added to a readable document.
        if (
            not RoleAccess(dt, user).is_unrestricted
            and await reference_readable(user, dt, data) is False
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=_("No access to the document")
            )

        now = datetime.now(UTC)
        doc_id, row = await self._build_initial_row(dt, table, data, user, now)

        _tokens = self._set_grunt_context(user)
        try:
            await self._persist_new_doc(dt, table, doctype_name, doc_id, data, row, user, now)
            await self._fire_create_services(doctype_name, dt, row)
        except IntegrityError as exc:
            raise friendly_integrity_error(exc, dt.doc) from exc
        finally:
            self._reset_grunt_context(_tokens)

        created = await self._serialize_doc_out(doctype_name, doc_id, row, dt)
        await self._fire_write_hooks("after_insert", "after_save", doctype_name, created, user)
        return created

    # update helpers

    def _build_update_payload(
        self,
        dt: Any,
        table: Any,
        data: dict[str, Any],
        user: User,
    ) -> dict[str, Any]:
        """Return the dict of fields to write into the DB (stripped + coerced)."""
        table_columns = {c.name for c in table.columns}
        update_data: dict[str, Any] = {}
        for field in dt.get_physical_fields():
            if field.fieldname not in table_columns:
                continue
            if field.fieldname in data and field.fieldname not in PROTECTED_FIELDS:
                update_data[field.fieldname] = field.coerce(data[field.fieldname])
        if "modified_at" in table.c:
            update_data["modified_at"] = datetime.now(UTC)
        if "modified_by" in table.c:
            update_data["modified_by"] = user.email
        return update_data

    async def _build_update_result(
        self,
        doctype_name: str,
        real_id: str,
        dt: Any,
        merged: dict[str, Any],
    ) -> dict[str, Any]:
        """Serialise, load child tables, and attach MultiLink fields for the response."""
        result = serialize_datetimes(dict(merged))
        await _load_child_tables(self.session, dt.doc, result)
        await attach_multi_link_values(self._ml, doctype_name, real_id, dt.doc, result)
        return result

    async def _persist_update_doc(
        self,
        dt: Any,
        table: Any,
        doctype_name: str,
        real_id: str,
        data: dict[str, Any],
        row: dict[str, Any],
        update_data: dict[str, Any],
        existing: dict[str, Any],
        user: User,
    ) -> None:
        """Apply update pipeline: formulas -> update row -> children -> aggregates -> MultiLink.

        Formulas are computed on *row* (the post-hook merged doc) and then a single
        pass copies every physical field that differs from *existing* into
        *update_data*. This captures both lifecycle-hook mutations and freshly
        computed formula values in one place before the UPDATE is issued.
        """
        await compute_formulas(dt.doc, row)

        table_cols = {c.name for c in table.columns}
        for field in dt.get_physical_fields():
            if field.fieldname in PROTECTED_FIELDS or field.fieldname not in table_cols:
                continue
            if row.get(field.fieldname) != existing.get(field.fieldname):
                update_data[field.fieldname] = row[field.fieldname]

        await self.session.execute(
            table.update().where(table.c.name == real_id).values(**update_data)
        )

        await _save_child_tables(self.session, dt.doc, real_id, row, user, datetime.now(UTC))
        await self._apply_aggregations(dt, table, real_id, row)

        await self._sync_multi_links(dt, doctype_name, real_id, data, only_present=True)

        await self.session.flush()

    # Update

    async def update_document(
        self,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
        user: User,
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        """Run the full update pipeline: hooks -> validate -> update -> hooks.

        Single entry point for updating a document - see :meth:`create_document`.
        """
        data = strip_file_signatures(data)
        # Optimistic-concurrency guard: the `modified_at` the client's edit was
        # based on (sent by offline replays). A newer server copy -> 409.
        base_modified_at = data.pop("__base_modified_at", None)
        dt = await self._resolve_dt(doctype_name)

        # A singleton's first save arrives here, not at ``create_document`` -
        # the form always routes it as an update (``doc_id`` == DocType name)
        # because there is no separate "new" state. Upsert: if the sole row
        # does not exist yet, create it now (named after the DocType).
        if dt.is_singleton and not is_virtual_routed(dt, doctype_name):
            table = dt.table
            count = await self.session.execute(select(func.count()).select_from(table))
            if (count.scalar() or 0) == 0:
                return await self.create_document(
                    doctype_name,
                    {**data, "name": dt.name},
                    user,
                    ignore_required=ignore_required,
                )

        await fire(
            "before_save",
            doctype=doctype_name,
            doc={"id": doc_id, **data},
            user=user,
            session=self.session,
        )

        if is_virtual_routed(dt, doctype_name):
            updated = await virtual_update(doctype_name, user, doc_id, data)
            await self._fire_write_hooks("after_update", "after_save", doctype_name, updated, user)
            return updated

        table = dt.table
        existing = await self.get_document(doctype_name, doc_id, user)

        # write_guard() (the facade's pre-check) only verifies doctype-level
        # access - it calls permission_checker with doc=None, so a
        # `match`-restricted write permission (e.g. "owner == user") is never
        # evaluated there. `existing` is already fetched for the diff logic
        # below, so this row-level check is free - no extra DB round trip.

        await permission_checker.require(user, dt, "write", existing)

        if base_modified_at and not _same_instant(base_modified_at, existing.get("modified_at")):
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
        auto_transition = await check_update(doctype_name, existing, data, user)

        errors = _validate_data(dt, data, partial=True, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        update_data = self._build_update_payload(dt, table, data, user)
        real_id = existing["name"]
        merged = {**existing, **update_data}
        # Inject submitted child-table rows into merged so lifecycle hooks see the
        # incoming data (not the old DB rows) and their mutations are persisted.
        # MultiLink lists too - visible to hooks, persisted from *data*.
        for _f in [*dt.get_child_table_fields(), *dt.get_multilink_fields()]:
            if _f.fieldname in data:
                merged[_f.fieldname] = data[_f.fieldname]

        _tokens = self._set_grunt_context(user)

        transition_token = _active.set(auto_transition) if auto_transition else None
        try:
            controller_cls = document_registry.get(doctype_name)
            doc = controller_cls(doctype_name, merged, user, self.session)
            await self._run_lifecycle_hooks(doc, "validate", "before_save")
            await self._require_user_permissions(dt, merged, user)
            await fill_route(dt, merged, self.session)

            # _persist_update_doc computes formulas then performs a single pass that
            # writes back every physical field differing from `existing` - capturing
            # both hook mutations (e.g. read-only computed fields) and formula values.
            await self._persist_update_doc(
                dt,
                table,
                doctype_name,
                real_id,
                data,
                merged,
                update_data,
                existing,
                user,
            )
            log.info("document.updated", doctype=doctype_name, id=real_id)

            result = await self._build_update_result(doctype_name, real_id, dt, merged)
            await record_update_changes(
                session=self.session,
                engine=self.engine,
                doctype_name=doctype_name,
                real_id=real_id,
                dt=dt,
                existing=existing,
                result=result,
                user=user,
            )

            doc.data = result
            await self._run_lifecycle_hooks(doc, "after_save")

            await fire_update_services(
                session=self.session,
                doctype_name=doctype_name,
                dt=dt.doc,
                result=result,
            )
            await self._fire_write_hooks("after_update", "after_save", doctype_name, result, user)
        except IntegrityError as exc:
            raise friendly_integrity_error(exc, dt.doc) from exc
        finally:
            if transition_token is not None:
                _active.reset(transition_token)
            self._reset_grunt_context(_tokens)

        if auto_transition:
            from grunt.workflow.engine import workflow_engine

            await workflow_engine.finish_transition(auto_transition, result, user, self.session)
        return result

    # Delete

    async def delete_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: User,
        replace_with: str | None = None,
    ) -> None:
        """Run the full delete pipeline: hooks -> delete -> hooks.

        Single entry point for deleting a document - see :meth:`create_document`.

        ``replace_with`` - id of a surviving document (same DocType) that every
        reference to the deleted document is repointed to before it is removed.
        """
        dt = await self._resolve_dt(doctype_name)
        if is_virtual_routed(dt, doctype_name):
            doc = {"name": doc_id}
            await fire(
                "before_delete", doctype=doctype_name, doc=doc, user=user, session=self.session
            )
            await virtual_delete(doctype_name, user, doc_id)
            await fire(
                "after_delete",
                doctype=doctype_name,
                doc_id=doc_id,
                doc=doc,
                user=user,
                session=self.session,
            )
            return

        table = dt.table

        existing = await self.get_document(doctype_name, doc_id, user)

        # Same reasoning as update_document: write_guard()'s pre-check can't
        # see `match`-restricted delete permissions (doc=None there); this
        # reuses the `existing` fetch already needed below, so it's free.

        await permission_checker.require(user, dt, "delete", existing)

        await check_delete(doctype_name, existing, user)

        real_id = existing["name"]

        if replace_with:
            from grunt.document.collection import repoint_references, validate_replacement

            await validate_replacement(self.session, dt, real_id, replace_with)
            try:
                await repoint_references(
                    self.session, dt, doctype_name, real_id, replace_with, is_merge=True
                )
                await self.session.flush()
            except IntegrityError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=_("Could not reassign the links: uniqueness conflict"),
                ) from exc

        await fire(
            "before_delete", doctype=doctype_name, doc=existing, user=user, session=self.session
        )

        # Custom Controller Hooks
        _tokens = self._set_grunt_context(user)
        try:
            controller_cls = document_registry.get(doctype_name)
            doc = controller_cls(doctype_name, existing, user, self.session)
            await self._run_lifecycle_hooks(doc, "before_delete")
            await delete_row_and_links(
                session=self.session,
                ml=self._ml,
                table=table,
                doctype_name=doctype_name,
                real_id=real_id,
            )
            await fire_delete_services(
                session=self.session,
                doctype_name=doctype_name,
                real_id=real_id,
                existing=existing,
            )
            await self._run_lifecycle_hooks(doc, "after_delete")

        finally:
            self._reset_grunt_context(_tokens)

        await fire(
            "after_delete",
            doctype=doctype_name,
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
